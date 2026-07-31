"""BlueDeer MCP 协议封装层：统一工具调用入口 + 审计日志。

P5 核心：所有工具调用收敛到 MCPClient.call，
链路 = 权限校验 → 静态扫描 → 执行 → 脱敏日志。
AuditLogger 用 JSON Lines 落盘，可回查、可统计。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from core.security import (
    RiskLevel,
    SecurityGuard,
    SecurityReport,
    sanitize_log,
)
from tools.base_tool import BaseTool, ToolCategory

logger = logging.getLogger("bluedeer.mcp")


# ============== AuditRecord：审计日志记录 ==============

@dataclass
class AuditRecord:
    """单次工具调用的审计记录。"""
    record_id: str = ""           # 审计记录 ID
    timestamp: float = 0.0
    agent_id: str = ""            # 调用方 Agent
    tool_name: str = ""           # 工具名
    category: str = ""            # 工具分级
    params_sanitized: dict[str, Any] = field(default_factory=dict)  # 脱敏后的参数
    status: str = ""              # allowed / denied / success / failed
    reason: str = ""              # 拒绝/失败原因
    risk_level: str = ""          # 扫描风险等级
    threat_count: int = 0         # 命中威胁数
    duration_ms: int = 0          # 执行耗时
    result_summary: str = ""      # 结果摘要（脱敏后）
    # T4 防篡改：SHA256 哈希链
    hash: str = ""                # 本条记录的 SHA256（含 prev_hash）
    prev_hash: str = ""           # 上一条记录的 hash

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============== AuditLogger：审计日志记录器 ==============

class AuditLogger:
    """审计日志记录器（JSON Lines 持久化）。

    每条记录一行 JSON，便于 grep / jq 查询。
    支持 SHA256 哈希链，提供防篡改验证。
    """

    def __init__(self, log_path: str = "logs/audit.jsonl") -> None:
        self._log_path = log_path
        self._buffer: list[AuditRecord] = []
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    def _compute_hash(self, record: AuditRecord, prev_hash: str) -> str:
        """计算记录的 SHA256 哈希（排除 hash 字段自身）。"""
        d = record.to_dict()
        d.pop("hash", None)
        d.pop("prev_hash", None)
        data = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256((prev_hash + data).encode("utf-8")).hexdigest()

    def log(self, record: AuditRecord) -> None:
        """记录一条审计日志（先入内存缓冲，同步落盘）。

        自动生成哈希链：
        - 从 buffer 取最后一条的 hash 作为 prev_hash
        - 计算本条的 hash
        """
        if not record.record_id:
            record.record_id = uuid.uuid4().hex[:16]
        if not record.timestamp:
            record.timestamp = time.time()
        # 哈希链
        record.prev_hash = self._buffer[-1].hash if self._buffer else ""
        record.hash = self._compute_hash(record, record.prev_hash)
        self._buffer.append(record)
        # 同步落盘（追加模式）
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("审计日志落盘失败（缓冲保留）: %s", e)

    def query(
        self,
        agent_id: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """查询审计日志。"""
        results: list[AuditRecord] = []
        for r in reversed(self._buffer):
            if agent_id and r.agent_id != agent_id:
                continue
            if tool_name and r.tool_name != tool_name:
                continue
            if status and r.status != status:
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def stats(self) -> dict[str, Any]:
        """审计统计：总数 / 各状态数 / 拒绝率。"""
        total = len(self._buffer)
        if total == 0:
            return {"total": 0}
        by_status: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        for r in self._buffer:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            by_tool[r.tool_name] = by_tool.get(r.tool_name, 0) + 1
        denied = by_status.get("denied", 0)
        return {
            "total": total,
            "by_status": by_status,
            "by_tool": by_tool,
            "deny_rate": round(denied / total, 4),
        }

    def verify(self) -> list[dict[str, Any]]:
        """验证哈希链完整性。

        遍历 buffer 中所有记录，检查每条记录的 hash 是否匹配
        SHA256(prev_hash + record_data)。

        Returns:
            问题记录列表。空列表表示完全通过。
        """
        issues: list[dict[str, Any]] = []
        for i, rec in enumerate(self._buffer):
            expected_prev = self._buffer[i - 1].hash if i > 0 else ""
            if rec.prev_hash != expected_prev:
                issues.append({
                    "index": i,
                    "record_id": rec.record_id,
                    "type": "broken_chain",
                    "detail": f"prev_hash 不匹配: 期望 {expected_prev[:16]}..., 实际 {rec.prev_hash[:16]}...",
                })
            # 重算 hash（排除 hash 和 prev_hash 字段）
            actual_hash = self._compute_hash(rec, rec.prev_hash)
            if rec.hash != actual_hash:
                issues.append({
                    "index": i,
                    "record_id": rec.record_id,
                    "type": "tampered",
                    "detail": f"hash 不匹配: 记录 {rec.hash[:16]}..., 实际 {actual_hash[:16]}...",
                })
        return issues

    def clear(self) -> None:
        """清空内存缓冲与磁盘日志文件。"""
        self._buffer.clear()
        try:
            if os.path.exists(self._log_path):
                open(self._log_path, "w").close()
        except OSError:
            pass


# ============== MCPClient：统一工具调用入口 ==============

@dataclass
class ToolMeta:
    """工具元数据。"""
    name: str = ""
    description: str = ""
    category: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """MCP 协议封装层：统一工具调用入口。

    链路：
    1. 工具查找（必须已注册）
    2. Agent 权限校验（SecurityGuard.check_permission）
    3. 操作安全校验（SecurityGuard.check_operation）
    4. 执行工具
    5. 脱敏 + 审计日志

    所有调用都经 AuditLogger 记录，可回查、可统计。
    """

    def __init__(
        self,
        guard: SecurityGuard | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._guard = guard or SecurityGuard()
        self._audit = audit_logger or AuditLogger()
        self._tools: dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """注册工具。"""
        if tool.name in self._tools:
            logger.warning("MCP 工具 %s 已注册，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        logger.info(
            "MCP 注册工具: %s (category=%s)",
            tool.name, tool.category.value,
        )

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def discover_tools(self) -> list[ToolMeta]:
        """返回所有已注册工具的元数据。"""
        metas: list[ToolMeta] = []
        for name, tool in self._tools.items():
            metas.append(ToolMeta(
                name=name,
                description=getattr(tool, "description", ""),
                category=getattr(tool, "category", ""),
                parameters=getattr(tool, "parameters", {}),
            ))
        return metas

    async def call_with_error_handling(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """带错误包装的工具调用。
        Args:
            tool_name: 工具名。
            args: 参数。
        Returns:
            统一响应 {"ok": bool, "result": Any, "reason": str}。
        """
        try:
            tool = self._tools.get(tool_name)
            if tool is None:
                return {"ok": False, "result": None, "reason": f"工具 {tool_name} 未注册"}
            result = await tool.execute(args)
            return {"ok": True, "result": result, "reason": "ok"}
        except KeyError as e:
            return {"ok": False, "result": None, "reason": f"参数缺失: {e}"}
        except Exception as e:
            return {"ok": False, "result": None, "reason": str(e)}

    def get_tool(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"MCP 工具 '{name}' 未注册")
        return self._tools[name]

    async def call(
        self,
        agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """统一调用入口。

        Args:
            agent_id: 调用方 Agent ID。
            tool_name: 工具名。
            params: 工具参数。

        Returns:
            {
                "ok": bool,
                "result": Any,        # 工具执行结果（成功时）
                "reason": str,        # 拒绝/失败原因
                "report": dict|None,  # 安全扫描报告
            }
        """
        t0 = time.time()
        params_sanitized = sanitize_log(params)
        tool = self._tools.get(tool_name)

        # 1. 工具存在性
        if tool is None:
            self._write_audit(
                agent_id, tool_name, "unknown", params_sanitized,
                "denied", "工具未注册", None, t0,
            )
            return {"ok": False, "reason": f"工具 '{tool_name}' 未注册", "result": None, "report": None}

        category = tool.category

        # 2. Agent 权限校验
        allowed, reason = self._guard.check_permission(agent_id, tool_name)
        if not allowed:
            self._write_audit(
                agent_id, tool_name, category.value, params_sanitized,
                "denied", reason, None, t0,
            )
            return {"ok": False, "reason": reason, "result": None, "report": None}

        # 3. 操作安全校验（HAZARDOUS 白名单 + 静态扫描）
        allowed, report, reason = self._guard.check_operation(
            tool_name, params, category,
        )
        report_dict = report.to_dict() if report else None
        if not allowed:
            self._write_audit(
                agent_id, tool_name, category.value, params_sanitized,
                "denied", reason, report, t0, report_dict,
            )
            return {"ok": False, "reason": reason, "result": None, "report": report_dict}

        # 4. 执行工具
        try:
            result = await tool.execute(params)
            self._write_audit(
                agent_id, tool_name, category.value, params_sanitized,
                "success", "ok", report, t0, report_dict,
                result_summary=_summarize(result),
            )
            return {
                "ok": True,
                "result": result,
                "reason": "ok",
                "report": report_dict,
            }
        except Exception as e:
            logger.exception("MCP 工具 %s 执行失败", tool_name)
            self._write_audit(
                agent_id, tool_name, category.value, params_sanitized,
                "failed", f"执行异常: {e}", report, t0, report_dict,
            )
            return {
                "ok": False,
                "reason": f"执行异常: {e}",
                "result": None,
                "report": report_dict,
            }

    # ---- 便捷访问 ----

    @property
    def guard(self) -> SecurityGuard:
        return self._guard

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    # ---- 内部 ----

    def _write_audit(
        self,
        agent_id: str,
        tool_name: str,
        category: str,
        params_sanitized: dict[str, Any],
        status: str,
        reason: str,
        report: SecurityReport | None,
        t0: float,
        report_dict: dict[str, Any] | None = None,
        result_summary: str = "",
    ) -> None:
        """构造并写入一条审计记录。"""
        record = AuditRecord(
            agent_id=agent_id,
            tool_name=tool_name,
            category=category,
            params_sanitized=params_sanitized,
            status=status,
            reason=reason,
            risk_level=report.risk_level.value if report else "safe",
            threat_count=len(report.threats) if report else 0,
            duration_ms=int((time.time() - t0) * 1000),
            result_summary=result_summary,
        )
        self._audit.log(record)


def _summarize(result: Any, max_len: int = 200) -> str:
    """对工具结果做摘要（脱敏后入库）。"""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        text = str(result)
    text = sanitize_log(text) if isinstance(text, str) else text  # type: ignore
    return text[:max_len] + ("..." if len(text) > max_len else "")
