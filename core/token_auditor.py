"""BlueDeer Token 审计模块：实时统计 Token 消耗，超限告警，月度报表。

P6 前置优化：
- 新增累计节省 Token 指标（低成本模型对比 baseline）
- 新增低成本模型调用占比
- 月度报表增加节省统计列
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from core.reward import RewardSystem

from core.config import get_config

logger = logging.getLogger("bluedeer.token")


@dataclass(slots=True)
class TokenRecord:
    """单次 Token 消耗记录。"""
    agent_id: str
    task_id: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


class TokenAuditor:
    """Token 审计器。

    实时统计每名员工、每条流水线、每轮梦境的 Token 消耗。
    超限告警，支持月度成本报表导出。
    """

    def __init__(self, threshold: int = get_config().reward.token_threshold) -> None:
        self._records: list[TokenRecord] = []
        self._threshold = threshold
        # P0 修复：超限回调（agent_id, task_id）→ None，用于触发上下文压缩
        self._overload_callback: Callable[[str, str], None] | None = None
        self._budgets: dict[str, int] = {}

    def set_overload_callback(self, callback: Callable[[str, str], None]) -> None:
        """P0 修复：注入超限回调。

        当 record() 触发 check_threshold 超限时，调用此回调。
        回调签名 (agent_id, task_id) -> None，典型用途是清理任务临时上下文。
        """
        self._overload_callback = callback

    def record(
        self,
        agent_id: str,
        task_id: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> TokenRecord:
        """记录一次 Token 消耗。

        P0 修复：若超限且已注入 overload callback，自动触发回调（典型用途：清理任务临时上下文）。
        """
        rec = TokenRecord(
            agent_id=agent_id,
            task_id=task_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self._records.append(rec)
        logger.info(
            "Token 记录: agent=%s, task=%s, model=%s, in=%d, out=%d",
            agent_id, task_id, model, tokens_in, tokens_out,
        )

        # P0 修复：超限触发回调（自动压缩上下文）
        if self._overload_callback is not None:
            exceeded, msg = self.check_threshold(task_id, rec.total)
            if exceeded:
                logger.warning("Token 超限触发回调: %s", msg)
                try:
                    self._overload_callback(agent_id, task_id)
                except Exception as e:
                    logger.warning("overload 回调执行失败: %s", e)

        return rec

    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        """获取某员工的 Token 统计。"""
        agent_records = [r for r in self._records if r.agent_id == agent_id]
        total_in = sum(r.tokens_in for r in agent_records)
        total_out = sum(r.tokens_out for r in agent_records)
        return {
            "agent_id": agent_id,
            "calls": len(agent_records),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_in + total_out,
            "by_model": self._by_model(agent_records),
        }

    def get_total_stats(self) -> dict[str, Any]:
        """获取全局 Token 统计。"""
        total_in = sum(r.tokens_in for r in self._records)
        total_out = sum(r.tokens_out for r in self._records)
        return {
            "total_calls": len(self._records),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_in + total_out,
            "by_agent": {
                agent_id: self.get_agent_stats(agent_id)
                for agent_id in {r.agent_id for r in self._records}
            },
        }

    def _by_model(self, records: list[TokenRecord]) -> dict[str, dict[str, int]]:
        """按模型分组统计。"""
        result: dict[str, dict[str, int]] = {}
        for r in records:
            if r.model not in result:
                result[r.model] = {"calls": 0, "tokens": 0}
            result[r.model]["calls"] += 1
            result[r.model]["tokens"] += r.total
        return result

    def check_threshold(self, task_id: str, tokens: int) -> tuple[bool, str]:
        """检查是否超限。

        Returns:
            (是否超限, 建议消息)
        """
        if tokens > self._threshold:
            return True, (
                f"任务 {task_id} Token 消耗 {tokens} 超过阈值 {self._threshold}，"
                f"建议拆分任务或压缩上下文"
            )
        return False, ""

    # ============== Usage/Budget API ==============

    def usage_stats(self, user_id: str, period: str = "all") -> dict[str, Any]:
        """返回用户 Token 用量摘要。
        Args:
            user_id: 员工 ID。
            period: 'all' | 'today' | 'this_week' | 'this_month'。
        Returns:
            用量摘要。
        """
        recs = [r for r in self._records if r.agent_id == user_id]
        if period != "all":
            now = time.time()
            cutoffs = {"today": 86400, "this_week": 604800, "this_month": 2592000}
            cutoff = cutoffs.get(period, 0)
            if cutoff:
                recs = [r for r in recs if now - r.timestamp <= cutoff]
        total = sum(r.total for r in recs)
        calls = len(recs)
        return {"agent_id": user_id, "period": period, "calls": calls, "tokens_total": total}

    def set_budget(self, user_id: str, limit: int) -> None:
        """设置每用户 Token 上限。
        Args:
            user_id: 员工 ID。
            limit: Token 限额。
        """
        self._budgets[user_id] = limit

    def budget_remaining(self, user_id: str) -> int:
        """计算用户剩余 Token 额度。
        Args:
            user_id: 员工 ID。
        Returns:
            剩余额度（无预算配置返回 -1）。
        """
        if user_id not in self._budgets:
            return -1
        used = sum(r.total for r in self._records if r.agent_id == user_id)
        return max(0, self._budgets[user_id] - used)

    def top_consumers(self, k: int = 5) -> list[dict[str, Any]]:
        """返回用 Token 最多的前 k 个用户。
        Args:
            k: 返回条数（默认 5）。
        Returns:
            [{agent_id, tokens_total}, ...]。
        """
        usage: dict[str, int] = {}
        for r in self._records:
            usage[r.agent_id] = usage.get(r.agent_id, 0) + r.total
        sorted_users = sorted(usage.items(), key=lambda x: -x[1])
        return [{"agent_id": uid, "tokens_total": t} for uid, t in sorted_users[:k]]

    # ============== P6 新增：节省与低成本指标 ==============

    def get_savings(self, agent_id: str | None = None) -> dict[str, Any]:
        """计算累计节省 Token。

        节省 = 估算 baseline Token - 实际 Token
        其中 baseline 估算：若用 Pro 模型，消耗 = 实际 * 1.5
        仅对低成本模型调用计入节省。

        Args:
            agent_id: 指定员工则只统计该员工，None 则全局。

        Returns:
            {
                "total_saved": int,          # 累计节省 Token
                "lowcost_calls": int,        # 低成本模型调用次数
                "total_calls": int,          # 总调用次数
                "by_agent": dict,            # 按员工分
            }
        """
        records = self._records
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]

        total_saved = 0
        lowcost_calls = 0
        by_agent: dict[str, dict[str, int]] = {}

        for r in records:
            agent = by_agent.setdefault(r.agent_id, {
                "saved": 0, "lowcost_calls": 0, "total_calls": 0,
            })
            agent["total_calls"] += 1
            if r.model in get_config().model.lowcost_models:
                lowcost_calls += 1
                agent["lowcost_calls"] += 1
                # 估算 baseline = 实际 * 倍率，节省 = baseline - 实际
                baseline = int(r.total * get_config().model.baseline_multiplier)
                saved = max(0, baseline - r.total)
                total_saved += saved
                agent["saved"] += saved

        return {
            "total_saved": total_saved,
            "lowcost_calls": lowcost_calls,
            "total_calls": len(records),
            "by_agent": by_agent,
        }

    def get_lowcost_ratio(self, agent_id: str | None = None) -> float:
        """计算低成本模型调用占比（0-100）。

        Args:
            agent_id: 指定员工则只统计该员工，None 则全局。

        Returns:
            占比百分比，0-100。
        """
        records = self._records
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        if not records:
            return 0.0
        lowcost = sum(1 for r in records if r.model in get_config().model.lowcost_models)
        return round(lowcost / len(records) * 100, 2)

    def sync_to_reward(self, agent_id: str, reward_system: "RewardSystem") -> None:
        """将本员工 Token 节省/低成本占比同步到奖惩系统。

        Args:
            agent_id: 员工 ID。
            reward_system: RewardSystem 实例。
        """
        savings = self.get_savings(agent_id)
        ratio = self.get_lowcost_ratio(agent_id)
        # 通过 RewardSystem 的更新方法写入档案
        reward_system.add_token_saved(agent_id, savings["total_saved"])
        reward_system.update_lowcost_ratio(agent_id, ratio)

    def export_monthly_report(self, year_month: str = "") -> str:
        """生成月度成本报表 Markdown。

        Args:
            year_month: 格式 YYYY-MM，默认当月。

        Returns:
            Markdown 格式报表字符串。
        """
        if not year_month:
            year_month = time.strftime("%Y-%m", time.localtime())

        # 过滤当月记录
        month_records = [
            r for r in self._records
            if time.strftime("%Y-%m", time.localtime(r.timestamp)) == year_month
        ]

        total_in = sum(r.tokens_in for r in month_records)
        total_out = sum(r.tokens_out for r in month_records)

        # P6 新增：节省统计
        savings = self.get_savings()
        month_lowcost = sum(
            1 for r in month_records if r.model in get_config().model.lowcost_models
        )
        lowcost_ratio = (
            round(month_lowcost / len(month_records) * 100, 2)
            if month_records else 0.0
        )

        lines = [
            f"# BlueDeer 月度 Token 成本报表",
            f"",
            f"**统计月份**: {year_month}",
            f"**总调用次数**: {len(month_records)}",
            f"**总输入 Token**: {total_in:,}",
            f"**总输出 Token**: {total_out:,}",
            f"**总 Token**: {total_in + total_out:,}",
            f"**低成本模型占比**: {lowcost_ratio}%",
            f"**累计节省 Token**: {savings['total_saved']:,}",
            f"",
            f"## 按员工统计",
            f"",
            f"| 员工 | 调用次数 | 输入 Token | 输出 Token | 总 Token | 节省 Token | 低成本占比 |",
            f"|------|----------|-----------|-----------|---------|-----------|-----------|",
        ]

        agent_ids = {r.agent_id for r in month_records}
        for agent_id in sorted(agent_ids):
            stats = self.get_agent_stats(agent_id)
            agent_savings = self.get_savings(agent_id)
            agent_ratio = self.get_lowcost_ratio(agent_id)
            lines.append(
                f"| {agent_id} | {stats['calls']} | "
                f"{stats['tokens_in']:,} | {stats['tokens_out']:,} | "
                f"{stats['tokens_total']:,} | "
                f"{agent_savings['total_saved']:,} | "
                f"{agent_ratio}% |"
            )

        lines.extend([
            f"",
            f"## 按模型统计",
            f"",
            f"| 模型 | 调用次数 | 总 Token |",
            f"|------|----------|---------|",
        ])

        model_stats = self._by_model(month_records)
        for model, stats in sorted(model_stats.items()):
            lines.append(f"| {model} | {stats['calls']} | {stats['tokens']:,} |")

        lines.extend([
            f"",
            f"## 详细记录",
            f"",
            f"| 时间 | 员工 | 任务 | 模型 | 输入 | 输出 |",
            f"|------|------|------|------|------|------|",
        ])
        for r in month_records:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.timestamp))
            lines.append(
                f"| {ts} | {r.agent_id} | {r.task_id} | {r.model} | "
                f"{r.tokens_in} | {r.tokens_out} |"
            )

        return "\n".join(lines)

    def save(self, path: str) -> None:
        """持久化到 JSON。"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            "threshold": self._threshold,
            "records": [asdict(r) for r in self._records],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> TokenAuditor:
        """从 JSON 加载。"""
        if not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        auditor = cls(threshold=data.get("threshold", get_config().reward.token_threshold))
        for rec_data in data.get("records", []):
            auditor._records.append(TokenRecord(**rec_data))
        return auditor

    def save_report(self, path: str, year_month: str = "") -> None:
        """保存月度报表到文件。"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        report = self.export_monthly_report(year_month)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)

    # ============== P4 扩容：日/周/月多维度报表 ==============

    def export_daily_report(self, date_str: str = "") -> str:
        """生成日报表 Markdown。

        Args:
            date_str: 格式 YYYY-MM-DD，默认当天。
        """
        if not date_str:
            date_str = time.strftime("%Y-%m-%d", time.localtime())
        day_records = [
            r for r in self._records
            if time.strftime("%Y-%m-%d", time.localtime(r.timestamp)) == date_str
        ]
        return self._format_period_report(
            f"日报表 {date_str}", day_records, "日",
        )

    def export_weekly_report(self, week_start: str = "") -> str:
        """生成周报表 Markdown。

        Args:
            week_start: 周一日期 YYYY-MM-DD，默认本周一。
        """
        import datetime
        if not week_start:
            today = datetime.date.today()
            monday = today - datetime.timedelta(days=today.weekday())
            week_start = monday.strftime("%Y-%m-%d")
        start = datetime.datetime.strptime(week_start, "%Y-%m-%d")
        end = start + datetime.timedelta(days=7)
        week_records = [
            r for r in self._records
            if start.timestamp() <= r.timestamp < end.timestamp()
        ]
        return self._format_period_report(
            f"周报表 {week_start} ~ {(start + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}",
            week_records, "周",
        )

    def export_multi_report(self) -> dict[str, str]:
        """一次性导出日/周/月三份报表。

        Returns:
            {"daily": str, "weekly": str, "monthly": str}
        """
        return {
            "daily": self.export_daily_report(),
            "weekly": self.export_weekly_report(),
            "monthly": self.export_monthly_report(),
        }

    def _format_period_report(
        self, title: str, records: list[TokenRecord], period: str,
    ) -> str:
        """格式化周期报表（日/周通用）。"""
        total_in = sum(r.tokens_in for r in records)
        total_out = sum(r.tokens_out for r in records)
        savings = self.get_savings()
        period_lowcost = sum(1 for r in records if r.model in get_config().model.lowcost_models)
        lowcost_ratio = (
            round(period_lowcost / len(records) * 100, 2) if records else 0.0
        )

        lines = [
            f"# BlueDeer Token {title}",
            "",
            f"**统计周期**: {period}",
            f"**调用次数**: {len(records)}",
            f"**输入 Token**: {total_in:,}",
            f"**输出 Token**: {total_out:,}",
            f"**总 Token**: {total_in + total_out:,}",
            f"**低成本占比**: {lowcost_ratio}%",
            f"**累计节省**: {savings['total_saved']:,}",
            "",
            "## 按员工",
            "",
            "| 员工 | 次数 | 输入 | 输出 | 总计 | 节省 | 低成本% |",
            "|------|------|------|------|------|------|---------|",
        ]
        for agent_id in sorted({r.agent_id for r in records}):
            agent_recs = [r for r in records if r.agent_id == agent_id]
            ai = sum(r.tokens_in for r in agent_recs)
            ao = sum(r.tokens_out for r in agent_recs)
            sv = self.get_savings(agent_id)["total_saved"]
            lr = self.get_lowcost_ratio(agent_id)
            lines.append(
                f"| {agent_id} | {len(agent_recs)} | {ai:,} | {ao:,} | {ai+ao:,} | {sv:,} | {lr}% |"
            )

        lines.extend([
            "",
            "## 按模型",
            "",
            "| 模型 | 次数 | 总 Token |",
            "|------|------|---------|",
        ])
        for model, stats in sorted(self._by_model(records).items()):
            lines.append(f"| {model} | {stats['calls']} | {stats['tokens']:,} |")

        return "\n".join(lines)
