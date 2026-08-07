"""commit 37：工具执行沙箱。

零基础读者可以这样理解：
- 当智能体决定调用某个工具时，本文件负责"安全地"执行它
- 安全 = 在独立线程中跑（不影响主线程）+ 超时自动停（默认 30 秒）
- 安全 = 危险工具（写文件/部署/网络）需要监工批准
- 安全 = stdout/stderr 被捕获，不污染主系统日志
- 工具执行的输入/输出/耗时/状态都记入日志，供前端展示

调用流程：
    ToolExecutor.execute(agent, "code_completion_lite",
                          {"prefix": "def "}, need_approval=False)
    ↓
    1. 查 tool_registry 拿到工具描述
    2. 校验 agent 是否绑定此工具
    3. 如需审批，挂起等待监工批准
    4. 在独立线程中调用 fallback 实现（或真实模块）
    5. 30 秒超时自动终止
    6. 返回 {ok, output, error, duration_ms, stdout, stderr}
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import io
import os
import sys
import threading
import time
import traceback
from typing import Any

# 默认超时 30 秒
DEFAULT_TIMEOUT = 30.0

# 需要监工审批的危险工具白名单
DANGEROUS_TOOLS = {
    "file_system_op",
    "sandbox_lite_exec",
    "http_lite_request",
    "grpc_lite_call",
    "websocket_lite_send",
    "certificate_sign",
    "bitcask_like_op",
    "mvcc_txn",
    "distributed_txn",
}

# commit 39：外部集成工具类型（git / shell / api）
# 这三种工具走 ExternalManager 的独立审批流（不进入 ToolExecutor 自带的审批）
EXTERNAL_TOOL_TYPES = {"git", "shell", "api"}

# 审批超时（30 分钟未响应自动拒绝）
APPROVAL_TIMEOUT = 30 * 60


# ----------------------------------------------------------------------
# 执行结果
# ----------------------------------------------------------------------


class ToolResult:
    """工具执行结果。"""

    __slots__ = (
        "agent_id",
        "duration_ms",
        "error",
        "ok",
        "output",
        "stderr",
        "stdout",
        "tool_name",
        "ts",
    )

    def __init__(
        self,
        ok: bool,
        output: Any = None,
        error: str = "",
        duration_ms: float = 0,
        stdout: str = "",
        stderr: str = "",
        tool_name: str = "",
        agent_id: str = "",
    ):
        self.ok = ok
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.stdout = stdout
        self.stderr = stderr
        self.tool_name = tool_name
        self.agent_id = agent_id
        self.ts = time.time()

    def to_dict(self) -> dict:
        # output 可能是任意类型，统一转 str 以便前端展示
        try:
            out_str = (
                self.output
                if isinstance(self.output, (str, int, float, bool, list, dict))
                else str(self.output)
            )
        except Exception:
            out_str = "<unserializable>"
        return {
            "ok": self.ok,
            "output": out_str,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "stdout": self.stdout[:2000] if self.stdout else "",
            "stderr": self.stderr[:2000] if self.stderr else "",
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "ts": self.ts,
        }


# ----------------------------------------------------------------------
# 审批管理
# ----------------------------------------------------------------------


class ApprovalRequest:
    """待审批的 dangerous 工具调用。"""

    __slots__ = (
        "_event",
        "agent_id",
        "agent_name",
        "created_ts",
        "decided_ts",
        "decision",
        "id",
        "params",
        "reason",
        "risk",
        "tool_name",
    )

    def __init__(
        self,
        rid: int,
        tool_name: str,
        agent_id: str,
        agent_name: str,
        params: dict,
        risk: str = "medium",
    ):
        self.id = rid
        self.tool_name = tool_name
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.params = params
        self.risk = risk
        self.created_ts = time.time()
        self.decision: str = ""  # "" / "approved" / "rejected"
        self.decided_ts: float = 0
        self.reason: str = ""
        self._event = threading.Event()

    def wait(self, timeout: float = APPROVAL_TIMEOUT) -> bool:
        """阻塞等待审批决定。返回 True 表示批准。"""
        if not self._event.wait(timeout=timeout):
            # 超时自动拒绝
            self.decision = "rejected"
            self.reason = "approval timeout (30 min)"
            self.decided_ts = time.time()
            return False
        return self.decision == "approved"

    def decide(self, decision: str, reason: str = "") -> None:
        self.decision = decision
        self.reason = reason
        self.decided_ts = time.time()
        self._event.set()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "params": self.params,
            "risk": self.risk,
            "created_ts": self.created_ts,
            "decision": self.decision,
            "decided_ts": self.decided_ts,
            "reason": self.reason,
        }


# ----------------------------------------------------------------------
# 工具执行器（单例）
# ----------------------------------------------------------------------


class ToolExecutor:
    """工具执行沙箱（单例）。

    所有智能体的工具调用都走这里，统一管理超时、审批、日志。
    """

    _instance: ToolExecutor | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pending_approvals: dict[int, ApprovalRequest] = {}
        self._history: list[ToolResult] = []  # 最近 200 条
        self._next_approval_id = 1
        # 历史日志的磁盘路径
        self._log_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
            "data",
            "tool_logs",
        )
        os.makedirs(self._log_dir, exist_ok=True)

    @classmethod
    def get_instance(cls) -> ToolExecutor:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------- 审批相关 ----------------

    def list_pending_approvals(self) -> list[dict]:
        with self._lock:
            return [
                a.to_dict() for a in self._pending_approvals.values() if not a.decision
            ]

    def get_approval(self, aid: int) -> ApprovalRequest | None:
        with self._lock:
            return self._pending_approvals.get(aid)

    def decide_approval(self, aid: int, decision: str, reason: str = "") -> bool:
        """监工做出审批决定。decision = 'approved' / 'rejected'。"""
        with self._lock:
            a = self._pending_approvals.get(aid)
        if a is None or a.decision:
            return False
        a.decide(decision, reason)
        return True

    # ---------------- 历史记录 ----------------

    def list_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._history[-limit:]]

    def _add_history(self, result: ToolResult) -> None:
        with self._lock:
            self._history.append(result)
            if len(self._history) > 200:
                self._history = self._history[-200:]

    # ---------------- 核心执行 ----------------

    def execute(
        self,
        agent: Any,
        tool_name: str,
        params: dict,
        need_approval: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        """执行工具调用。

        Args:
            agent: 调用工具的智能体实例（需要 species / get_agent_id / _name_obj 字段）
            tool_name: 工具名
            params: 调用参数
            need_approval: 是否需要审批（None 时按 DANGEROUS_TOOLS 自动判断）
            timeout: 超时秒数
        """
        # DANGEROUS_TOOLS 是本文件模块级常量，直接使用
        from core.digital_life.tool_registry import get_tool_registry

        registry = get_tool_registry()

        agent_id = ""
        agent_name = ""
        species = ""
        if agent is not None:
            try:
                agent_id = agent.get_agent_id()
            except Exception:
                agent_id = ""
            agent_name = getattr(agent, "_name_obj", "") or ""
            species = getattr(agent, "species", "") or ""

        # 1. 校验工具存在
        tool_desc = registry.get_tool(tool_name)
        if tool_desc is None:
            return ToolResult(
                False,
                error="tool not found: " + tool_name,
                tool_name=tool_name,
                agent_id=agent_id,
            )
        # 2. 校验 agent 是否绑定此工具（不严格，未绑定也允许，但记 stderr）
        bound = registry.list_tool_names_for_species(species) if species else []
        warning = ""
        if bound and tool_name not in bound:
            warning = (
                f"warning: tool {tool_name} not in {species}'s bound tools, "
                f"executing anyway"
            )

        # 3. 审批判断
        if need_approval is None:
            need_approval = tool_name in DANGEROUS_TOOLS
        if need_approval:
            approval = self._request_approval(tool_name, agent_id, agent_name, params)
            approved = approval.wait()
            if not approved:
                result = ToolResult(
                    False,
                    error="rejected by supervisor: " + approval.reason,
                    tool_name=tool_name,
                    agent_id=agent_id,
                )
                self._add_history(result)
                return result

        # 4. 在独立线程中执行
        return self._run_in_sandbox(tool_name, params, agent_id, timeout, warning)

    # ---------------- commit 39：外部集成（git/shell/api）----------------

    def execute_external(self, agent: Any, op_type: str, params: dict) -> ToolResult:
        """执行外部集成工具调用（git / shell / api）。

        零基础理解：本方法把 git/shell/api 三类外部操作统一交给
        ExternalManager 处理。ExternalManager 内部自带审批工作流
        （读类放行、写类挂审批、30 分钟超时自动拒绝），不与本类的
        ApprovalRequest 重复审批。

        Args:
            agent: 调用方智能体实例
            op_type: "git" / "shell" / "api"
            params: {
                git:   {"args": ["status"], "summary": "...", "risk_level": "low"}
                shell: {"command": "pytest -x", "summary": "...", "risk_level": "medium"}
                api:   {"endpoint": "github_api", "method": "GET",
                        "path": "/repos/...", "summary": "...", "risk_level": "low"}
            }

        Returns:
            ToolResult（ok=True 表示外部集成受理并执行成功；
                       ok=False 表示被拒绝/超时/执行出错，error 字段说明原因）
        """
        from core.digital_life.external import get_external_manager

        agent_id = ""
        if agent is not None:
            try:
                agent_id = agent.get_agent_id()
            except Exception:
                agent_id = ""
            getattr(agent, "_name_obj", "") or ""
            getattr(agent, "species", "") or ""

        mgr = get_external_manager()
        start = time.time()
        summary = params.get("summary", "") or f"{op_type} op"
        risk_level = params.get("risk_level", "medium")
        result_obj: Any = None
        error_msg = ""
        try:
            if op_type == "git":
                args = list(params.get("args", []) or [])
                result_obj = mgr.execute_git(
                    agent=agent,
                    args=args,
                    summary=summary,
                    risk_level=risk_level,
                )
            elif op_type == "shell":
                command = str(params.get("command", "") or "")
                result_obj = mgr.execute_shell(
                    agent=agent,
                    command=command,
                    summary=summary,
                    risk_level=risk_level,
                )
            elif op_type == "api":
                endpoint = str(params.get("endpoint", "") or "")
                method = str(params.get("method", "GET") or "GET").upper()
                path = str(params.get("path", "") or "")
                query = params.get("query")
                body = params.get("body")
                result_obj = mgr.call_api(
                    agent=agent,
                    endpoint=endpoint,
                    method=method,
                    path=path,
                    query=query,
                    body=body,
                    summary=summary,
                    risk_level=risk_level,
                )
            else:
                error_msg = f"unknown external op_type: {op_type}"
        except Exception as e:
            error_msg = f"execute_external 异常: {e}\n{traceback.format_exc()}"

        duration_ms = (time.time() - start) * 1000

        # ExternalManager 返回的对象可能是 GitResult/ShellResult/ApiResult/ApprovalRequest/dict
        ok = False
        output: Any = None
        stdout = ""
        stderr = ""
        if error_msg:
            stderr = error_msg
        elif result_obj is None:
            stderr = "external manager returned None"
        else:
            # 各种 Result 对象都有 .ok 字段
            ok = bool(getattr(result_obj, "ok", False))
            # 优先取 stdout/stderr（git/shell），其次取 response_body（api）
            stdout = (
                getattr(result_obj, "stdout", "")
                or getattr(result_obj, "response_body", "")
                or ""
            )
            stderr = (
                getattr(result_obj, "stderr", "")
                or getattr(result_obj, "error", "")
                or ""
            )
            # 如果是 ApprovalRequest（写类挂审批中），result_obj.decision 决定 ok
            decision = getattr(result_obj, "decision", "")
            if decision == "rejected":
                ok = False
                stderr = (
                    "rejected by supervisor: "
                    + getattr(result_obj, "decision_reason", "")
                    or "approval rejected"
                )
            elif decision == "approved":
                # 已审批通过：result_obj 实际是 ApprovalRequest，需取 result 字段
                actual = getattr(result_obj, "result", None)
                if actual is not None:
                    ok = bool(getattr(actual, "ok", False))
                    stdout = (
                        getattr(actual, "stdout", "")
                        or getattr(actual, "response_body", "")
                        or ""
                    )
                    stderr = (
                        getattr(actual, "stderr", "")
                        or getattr(actual, "error", "")
                        or ""
                    )
                else:
                    ok = True
            elif decision == "":
                # 还在等待审批 → 视为挂起，不算成功
                ok = False
                stderr = "approval still pending or timeout"
            output = result_obj

        tool_name_full = f"external_{op_type}"
        result = ToolResult(
            ok=ok,
            output=output,
            error=stderr,
            duration_ms=duration_ms,
            stdout=str(stdout)[:2000],
            stderr=str(stderr)[:2000],
            tool_name=tool_name_full,
            agent_id=agent_id,
        )
        self._add_history(result)
        return result

    def _request_approval(
        self, tool_name: str, agent_id: str, agent_name: str, params: dict
    ) -> ApprovalRequest:
        with self._lock:
            aid = self._next_approval_id
            self._next_approval_id += 1
            risk = (
                "high"
                if tool_name in ("file_system_op", "sandbox_lite_exec")
                else "medium"
            )
            a = ApprovalRequest(aid, tool_name, agent_id, agent_name, params, risk)
            self._pending_approvals[aid] = a
        return a

    def _run_in_sandbox(
        self,
        tool_name: str,
        params: dict,
        agent_id: str,
        timeout: float,
        warning: str = "",
    ) -> ToolResult:
        """在独立线程中执行工具，捕获 stdout/stderr，超时终止。"""
        from core.digital_life.tool_registry import FALLBACK_IMPLEMENTATIONS

        start = time.time()
        out_box: dict = {}
        # 用一个事件 + 子线程实现超时
        done_evt = threading.Event()

        def _runner():
            # 捕获 stdout/stderr
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            try:
                impl = FALLBACK_IMPLEMENTATIONS.get(tool_name)
                if impl is None:
                    out_box["output"] = {
                        "simulated": True,
                        "summary": f"工具 {tool_name} 无兜底实现，返回模拟结果",
                    }
                    return
                # 调用，过滤 params 中 None 值
                clean_params = {k: v for k, v in params.items() if v is not None}
                # 只传 fallback 实现实际接受的参数（避免 func_name 这类
                # 工具描述里有但 fallback 签名里没有的参数导致 TypeError）
                import inspect as _inspect

                try:
                    sig = _inspect.signature(impl)
                    accepts_kwargs = any(
                        p.kind == _inspect.Parameter.VAR_KEYWORD
                        for p in sig.parameters.values()
                    )
                    if not accepts_kwargs:
                        valid_keys = set(sig.parameters.keys())
                        clean_params = {
                            k: v for k, v in clean_params.items() if k in valid_keys
                        }
                except (ValueError, TypeError):
                    logger.exception("Exception in block")
                    pass
                result = impl(**clean_params)
                out_box["output"] = result
            except Exception as e:
                out_box["error"] = str(e) + "\n" + traceback.format_exc()
            finally:
                out_box["stdout"] = sys.stdout.getvalue() or ""
                out_box["stderr"] = sys.stderr.getvalue() or ""
                sys.stdout, sys.stderr = old_out, old_err
                done_evt.set()

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        # 等待完成或超时
        if not done_evt.wait(timeout=timeout):
            # 超时（线程仍在跑，但作为 daemon 不会阻塞进程退出）
            duration = (time.time() - start) * 1000
            result = ToolResult(
                False,
                error="timeout after " + str(timeout) + "s",
                duration_ms=duration,
                tool_name=tool_name,
                agent_id=agent_id,
            )
            self._add_history(result)
            return result

        duration = (time.time() - start) * 1000
        if "error" in out_box:
            result = ToolResult(
                False,
                error=out_box["error"],
                duration_ms=duration,
                stdout=out_box.get("stdout", ""),
                stderr=(warning + "\n" if warning else "") + out_box.get("stderr", ""),
                tool_name=tool_name,
                agent_id=agent_id,
            )
        else:
            result = ToolResult(
                True,
                output=out_box.get("output"),
                duration_ms=duration,
                stdout=out_box.get("stdout", ""),
                stderr=(warning + "\n" if warning else "") + out_box.get("stderr", ""),
                tool_name=tool_name,
                agent_id=agent_id,
            )
        self._add_history(result)
        return result

    # ------------------------------------------------------------------
    # commit 42：execute_safe 沙箱包装
    # ------------------------------------------------------------------

    def execute_safe(
        self, name: str, args: dict | None = None, timeout: float = 30.0
    ) -> ExecutionResult:
        start = time.time()
        try:
            raw = self.execute(name, params=args, timeout=timeout)
            duration = (time.time() - start) * 1000
            if raw.ok:
                return ExecutionResult(name, True, raw.output, duration, raw.stdout, "")
            return ExecutionResult(
                name, False, None, duration, raw.stdout, raw.error or "execution failed"
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(name, False, None, duration, "", str(e))


class ExecutionResult:
    __slots__ = ("duration_ms", "error", "output", "stdout", "success", "tool_name")

    def __init__(
        self,
        tool_name: str,
        success: bool,
        output: Any,
        duration_ms: float,
        stdout: str,
        error: str,
    ):
        self.tool_name = tool_name
        self.success = success
        self.output = output
        self.duration_ms = duration_ms
        self.stdout = stdout
        self.error = error

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def get_tool_executor() -> ToolExecutor:
    return ToolExecutor.get_instance()
