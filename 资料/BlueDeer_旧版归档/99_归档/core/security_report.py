"""BlueDeer 安全报告：结构化输出 + 阈值判定 + markdown 导出。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from core.security_scanner import RiskLevel, SecurityReport, SecurityScanner

logger = logging.getLogger("bluedeer.security_report")


@dataclass
class SecurityThresholds:
    fail_on_high: bool = True
    max_medium: int = 5
    max_total: int = 20
    high_risk_agents_blocked: bool = True


class SecurityReportBuilder:
    def __init__(
        self,
        scanner: SecurityScanner | None = None,
        thresholds: SecurityThresholds | None = None,
    ) -> None:
        self._scanner = scanner or SecurityScanner()
        self._thresholds = thresholds or SecurityThresholds()

    def build_for_text(self, text: str, target: str = "") -> SecurityReport:
        return self._scanner.scan_all(text, target=target or text[:50])

    def build_for_agent_output(
        self, agent_id: str, output: dict[str, Any]
    ) -> SecurityReport:
        flattened = " ".join(
            str(v) for v in output.values() if isinstance(v, (str, int, float))
        )
        return self._scanner.scan_all(flattened, target=f"agent:{agent_id}")

    def is_acceptable(self, report: SecurityReport) -> tuple[bool, str]:
        thresholds = self._thresholds
        if thresholds.fail_on_high and any(
            t.risk == RiskLevel.HIGH for t in report.threats
        ):
            high_types = [
                t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH
            ]
            return False, f"blocked: high-risk threats {high_types}"
        medium_count = sum(1 for t in report.threats if t.risk == RiskLevel.MEDIUM)
        if medium_count > thresholds.max_medium:
            return (
                False,
                f"blocked: medium threats {medium_count} > {thresholds.max_medium}",
            )
        if len(report.threats) > thresholds.max_total:
            return (
                False,
                f"blocked: total threats {len(report.threats)} > {thresholds.max_total}",
            )
        return True, "ok"

    def to_markdown(self, report: SecurityReport) -> str:
        lines = [
            f"# Security Report: {report.target}",
            f"- risk_level: {report.risk_level.value}",
            f"- passed: {report.passed}",
            f"- threat_count: {len(report.threats)}",
            f"- scanned_at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report.scanned_at))}",
            "",
            "## Threats",
        ]
        if not report.threats:
            lines.append("_none_")
        else:
            for t in report.threats:
                lines.append(
                    f"- **{t.threat_type}** ({t.risk.value}): `{t.matched}` @ {t.location}"
                )
        return "\n".join(lines)

    def summary(self, report: SecurityReport) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for t in report.threats:
            counts[t.threat_type] = counts.get(t.threat_type, 0) + 1
        return {
            "target": report.target,
            "risk_level": report.risk_level.value,
            "passed": report.passed,
            "threat_count": len(report.threats),
            "by_type": counts,
            "scanned_at": report.scanned_at,
        }


# ============== P5 扩容：SecurityReportGenerator 月度安全报告（P2-1 移入） ==============


@dataclass
class SecurityAuditRecord:
    """P5 扩容：单次安全审计记录（用于月报聚合）。"""

    timestamp: float
    target: str
    risk_level: str  # safe/low/medium/high
    threat_count: int
    threat_types: list[str]  # ["sql_injection", "xss", ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "target": self.target,
            "risk_level": self.risk_level,
            "threat_count": self.threat_count,
            "threat_types": self.threat_types,
            "passed": self.passed,
        }


class SecurityReportGenerator:
    """P5 扩容：月度安全风险汇总报告生成器。

    职责：
    - 收集 SecurityReport / SecurityAuditRecord
    - 按威胁类型 / 风险等级 / 时间段聚合统计
    - 生成 Markdown 月度报告（含 TopN 高危目标、趋势、建议）
    """

    def __init__(self) -> None:
        self._records: list[SecurityAuditRecord] = []

    def add_report(self, report: SecurityReport) -> None:
        """从 SecurityReport 转换并追加记录。"""
        threat_types = []
        for t in report.threats:
            # threat_type 形如 "secret_leak:api_key"，取冒号前的大类
            base = t.threat_type.split(":")[0]
            if base not in threat_types:
                threat_types.append(base)
        self._records.append(
            SecurityAuditRecord(
                timestamp=report.scanned_at,
                target=report.target,
                risk_level=report.risk_level.value,
                threat_count=len(report.threats),
                threat_types=threat_types,
                passed=report.passed,
            )
        )

    def add_audit_record(self, record: SecurityAuditRecord) -> None:
        """直接追加审计记录。"""
        self._records.append(record)

    def clear(self) -> None:
        """清空记录。"""
        self._records.clear()

    @property
    def record_count(self) -> int:
        return len(self._records)

    def stats(self) -> dict[str, Any]:
        """聚合统计。"""
        if not self._records:
            return {
                "total": 0,
                "by_risk": {},
                "by_threat_type": {},
                "blocked_count": 0,
                "pass_rate": 0.0,
            }
        by_risk: dict[str, int] = {"safe": 0, "low": 0, "medium": 0, "high": 0}
        by_threat: dict[str, int] = {}
        blocked = 0
        passed = 0
        for r in self._records:
            by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1
            if not r.passed:
                blocked += 1
            else:
                passed += 1
            for t in r.threat_types:
                by_threat[t] = by_threat.get(t, 0) + 1
        return {
            "total": len(self._records),
            "by_risk": by_risk,
            "by_threat_type": by_threat,
            "blocked_count": blocked,
            "pass_rate": round(passed / len(self._records), 4),
        }

    def top_targets(self, n: int = 5) -> list[tuple[str, int]]:
        """TopN 高危目标（按 threat_count 降序）。"""
        sorted_recs = sorted(
            self._records,
            key=lambda r: r.threat_count,
            reverse=True,
        )
        return [(r.target, r.threat_count) for r in sorted_recs[:n]]

    def generate_markdown(self, period_label: str = "本月") -> str:
        """生成 Markdown 月度安全报告。

        Args:
            period_label: 报告周期标签（如 "2026-07"）。

        Returns:
            Markdown 字符串。
        """
        s = self.stats()
        lines: list[str] = [
            f"# 安全审计月度报告（{period_label}）",
            "",
            f"**审计次数**: {s['total']}",
            f"**拦截次数**: {s['blocked_count']}",
            f"**通过率**: {s['pass_rate'] * 100:.1f}%",
            "",
            "## 风险等级分布",
            "",
            "| 风险等级 | 次数 |",
            "|---|---|",
        ]
        for level in ("high", "medium", "low", "safe"):
            count = s["by_risk"].get(level, 0)
            lines.append(f"| {level} | {count} |")
        lines.append("")
        lines.append("## 威胁类型分布")
        lines.append("")
        lines.append("| 威胁类型 | 次数 |")
        lines.append("|---|---|")
        # 按次数降序
        sorted_threats = sorted(s["by_threat_type"].items(), key=lambda x: -x[1])
        for t, c in sorted_threats:
            lines.append(f"| {t} | {c} |")
        lines.append("")
        lines.append("## Top 5 高危目标")
        lines.append("")
        lines.append("| 目标 | 威胁数 |")
        lines.append("|---|---|")
        for target, count in self.top_targets(5):
            lines.append(f"| {target} | {count} |")
        lines.append("")
        lines.append("## 建议")
        lines.append("")
        if s["blocked_count"] > 0:
            lines.append(
                f"- 本期拦截 {s['blocked_count']} 次高危操作，建议复盘参数来源。"
            )
        if s["by_threat_type"].get("sql_injection", 0) > 0:
            lines.append("- SQL 注入命中较多，建议推广参数化查询。")
        if s["by_threat_type"].get("secret_leak", 0) > 0:
            lines.append("- 密钥泄露命中较多，建议接入密钥管理服务。")
        if s["by_threat_type"].get("unsafe_api", 0) > 0:
            lines.append(
                "- 不安全 API（eval/pickle 等）命中较多，建议代码评审强化禁用清单。"
            )
        if not lines[-1].startswith("-"):
            lines.append("- 本期无高危命中，继续保持。")
        return "\n".join(lines) + "\n"
