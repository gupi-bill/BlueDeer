"""告警规则引擎。

基于系统指标和审计事件匹配规则，触发告警通知。
规则支持：阈值比较、变化率、持续时长、频率限制。
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
# ruff: noqa: S110, S112

logger = logging.getLogger("bluedeer.alert")

_ALERTS_FILE = "logs/alerts.jsonl"


@dataclass
class AlertRule:
    id: str
    name: str
    metric: str
    operator: str  # gt, lt, gte, lte, eq
    threshold: float
    duration_sec: float = 0
    cooldown_sec: float = 300
    enabled: bool = True
    severity: str = "warning"  # info, warning, critical
    message_template: str = "{name}: {metric} = {value} (阈值 {op} {threshold})"


@dataclass
class AlertEvent:
    rule_id: str
    rule_name: str
    metric: str
    value: float
    severity: str
    message: str
    ts: float = field(default_factory=time.time)
    acknowledged: bool = False


class AlertEngine:
    def __init__(self, alerts_file: str = _ALERTS_FILE) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._history: dict[str, float] = {}  # rule_id -> last trigger ts
        self._suppress_until: dict[str, float] = {}  # rule_id -> suppress until ts
        self._fire_count: dict[str, int] = (
            {}
        )  # rule_id -> consecutive fire count (for escalation)
        self._alerts_file = alerts_file
        self._callbacks: list[Callable[[AlertEvent], None]] = []
        self._load_rules()
        os.makedirs(os.path.dirname(self._alerts_file) or ".", exist_ok=True)

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def get_rule(self, rule_id: str) -> AlertRule | None:
        return self._rules.get(rule_id)

    def list_rules(self) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "name": r.name,
                "metric": r.metric,
                "operator": r.operator,
                "threshold": r.threshold,
                "duration_sec": r.duration_sec,
                "cooldown_sec": r.cooldown_sec,
                "enabled": r.enabled,
                "severity": r.severity,
            }
            for r in self._rules.values()
        ]

    # ---- 抑制规则 ----

    def suppress(self, rule_id: str, duration: float = 300) -> bool:
        """临时抑制某规则的告警触发，持续 duration 秒。"""
        if rule_id not in self._rules:
            return False
        self._suppress_until[rule_id] = time.time() + duration
        logger.info("告警规则 %s 已抑制 %.0fs", rule_id, duration)
        return True

    def unsuppress(self, rule_id: str) -> bool:
        """取消抑制。"""
        return self._suppress_until.pop(rule_id, None) is not None

    def _is_suppressed(self, rule_id: str) -> bool:
        until = self._suppress_until.get(rule_id, 0)
        return time.time() < until

    # ---- 升级策略 ----

    _ESCALATION_MAP: dict[str, str] = {
        "info": "warning",
        "warning": "critical",
        "critical": "critical",
    }

    def escalate(self, rule_id: str) -> bool:
        """手动提升某规则的下一次告警 severity。

        如规则已 critical 则保持。
        """
        rule = self._rules.get(rule_id)
        if not rule:
            return False
        new_sev = self._ESCALATION_MAP.get(rule.severity, "critical")
        if new_sev != rule.severity:
            rule.severity = new_sev
            logger.info("告警规则 %s 已升级 severity -> %s", rule_id, new_sev)
        return True

    def _update_fire_count(self, rule_id: str, triggered: bool) -> None:
        """跟踪连续触发次数用于自动升级。"""
        if triggered:
            self._fire_count[rule_id] = self._fire_count.get(rule_id, 0) + 1
            # 连续触发 >=3 次自动升级
            if self._fire_count[rule_id] >= 3:
                rule = self._rules.get(rule_id)
                if rule and rule.severity != "critical":
                    rule.severity = self._ESCALATION_MAP.get(rule.severity, "critical")
                    logger.warning(
                        "告警规则 %s 连续触发 %d 次，自动升级为 %s",
                        rule_id,
                        self._fire_count[rule_id],
                        rule.severity,
                    )
        else:
            self._fire_count[rule_id] = 0

    def on_alert(self, cb: Callable[[AlertEvent], None]) -> None:
        self._callbacks.append(cb)

    def evaluate(self, metric: str, value: float) -> AlertEvent | None:
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.metric != metric:
                continue

            triggered = self._check_threshold(value, rule.operator, rule.threshold)
            self._update_fire_count(rule.id, triggered)
            if not triggered:
                continue

            if self._in_cooldown(rule):
                continue

            if self._is_suppressed(rule.id):
                logger.debug("告警规则 %s 当前被抑制，跳过", rule.id)
                continue

            event = AlertEvent(
                rule_id=rule.id,
                rule_name=rule.name,
                metric=metric,
                value=value,
                severity=rule.severity,
                message=rule.message_template.format(
                    name=rule.name,
                    metric=metric,
                    value=value,
                    op=rule.operator,
                    threshold=rule.threshold,
                ),
            )
            self._history[rule.id] = time.time()
            self._persist(event)

            for cb in self._callbacks:
                try:
                    cb(event)
                except Exception:
                    logger.exception("告警回调异常")

            return event
        return None

    def recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        if not os.path.exists(self._alerts_file):
            return []
        result: list[dict[str, Any]] = []
        try:
            with open(self._alerts_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        result.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            pass
        result.sort(key=lambda e: e.get("ts", 0), reverse=True)
        return result[:limit]

    def acknowledge(self, rule_id: str) -> None:
        entries = self.recent_alerts(limit=200)
        for e in entries:
            if e.get("rule_id") == rule_id:
                e["acknowledged"] = True
        self._rewrite(entries)

    def _check_threshold(self, value: float, op: str, threshold: float) -> bool:
        if op == "gt":
            return value > threshold
        elif op == "lt":
            return value < threshold
        elif op == "gte":
            return value >= threshold
        elif op == "lte":
            return value <= threshold
        elif op == "eq":
            return abs(value - threshold) < 0.001
        return False

    def _in_cooldown(self, rule: AlertRule) -> bool:
        last = self._history.get(rule.id, 0)
        return (time.time() - last) < rule.cooldown_sec

    def _persist(self, event: AlertEvent) -> None:
        try:
            with open(self._alerts_file, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "rule_id": event.rule_id,
                            "rule_name": event.rule_name,
                            "metric": event.metric,
                            "value": event.value,
                            "severity": event.severity,
                            "message": event.message,
                            "ts": event.ts,
                            "acknowledged": event.acknowledged,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError as e:
            logger.warning("告警持久化失败: %s", e)

    def _rewrite(self, entries: list[dict]) -> None:
        try:
            with open(self._alerts_file, "w", encoding="utf-8") as f:
                f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
        except OSError:
            pass

    def _load_rules(self) -> None:
        try:
            from core.config import get_config

            cfg = get_config().alerts
            if not cfg.enabled:
                return
            for r in getattr(cfg, "default_rules", []):
                self.add_rule(AlertRule(**r))
        except Exception:
            pass


# 全局单例
_alert_engine: AlertEngine | None = None


def get_alert_engine() -> AlertEngine:
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine
