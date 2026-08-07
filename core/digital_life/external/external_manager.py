"""commit 39：外部集成总控（统一管理 Git / Shell / API 三种集成的开关和审批）。

零基础读者可以这样理解：
- 三种外部集成（Git / Shell / API）都是危险的——能改真实世界
- ExternalManager 是它们的"总门卫"
- 默认全部关闭，监工要逐个开启
- 危险操作（写文件 / push / POST）需要审批
- 审批请求排队等监工响应

数据持久化：
- data/external_config.json：开关和配置
- data/external_approvals.json：审批历史
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

from core.digital_life.external.api_caller import ApiCaller
from core.digital_life.external.git_integration import GitIntegration
from core.digital_life.external.shell_executor import ShellExecutor
# ruff: noqa: S110, S112

_CONFIG_PATH = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
    "data",
    "external_config.json",
)

_APPROVALS_PATH = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
    "data",
    "external_approvals.json",
)

# 审批超时（30 分钟未响应自动拒绝）
_APPROVAL_TIMEOUT = 30 * 60

# 风险等级
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

# 操作类型
OP_GIT = "git"
OP_SHELL = "shell"
OP_API = "api"


# 默认配置（全部关闭）
_DEFAULT_CONFIG = {
    "git": {
        "enabled": False,
        "repo_path": "",
        "auto_commit": False,
        "require_approval": True,
        "allow_dangerous": False,
    },
    "shell": {
        "enabled": False,
        "whitelist": [
            "python",
            "python3",
            "pytest",
            "pip",
            "npm",
            "node",
            "yarn",
            "git",
            "ls",
            "cat",
            "echo",
            "grep",
            "find",
            "head",
            "tail",
            "wc",
            "mkdir",
            "cp",
            "mv",
            "touch",
        ],
        "blacklist": ["rm -rf", "sudo", "chmod 777", "curl ", "wget "],
        "timeout": 60,
        "workdir": "",
        "require_approval": True,
    },
    "api": {
        "enabled": False,
        "endpoints": [],
        "require_approval": True,
    },
}


class ApprovalRequest:
    """审批请求。"""

    __slots__ = (
        "agent_id",
        "agent_name",
        "created_ts",
        "decided_ts",
        "decision",
        "decision_reason",
        "detail",
        "id",
        "op_type",
        "result",
        "risk_level",
        "species",
        "summary",
    )

    def __init__(
        self,
        op_type: str,
        agent_id: str,
        agent_name: str,
        species: str,
        summary: str,
        detail: dict,
        risk_level: str = RISK_MEDIUM,
    ) -> None:
        self.id: str = "ap-" + uuid.uuid4().hex[:8]
        self.op_type: str = op_type
        self.agent_id: str = agent_id
        self.agent_name: str = agent_name
        self.species: str = species
        self.summary: str = summary
        self.detail: dict = detail
        self.risk_level: str = risk_level
        self.created_ts: float = time.time()
        self.decision: str = ""  # "" / "approved" / "rejected"
        self.decided_ts: float = 0.0
        self.decision_reason: str = ""
        self.result: dict = {}  # 执行结果（审批通过后填充）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "op_type": self.op_type,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "species": self.species,
            "summary": self.summary,
            "detail": self.detail,
            "risk_level": self.risk_level,
            "created_ts": self.created_ts,
            "decision": self.decision,
            "decided_ts": self.decided_ts,
            "decision_reason": self.decision_reason,
            "result": self.result,
        }


class ExternalManager:
    """外部集成总控（单例）。"""

    _instance: ExternalManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config: dict = {}
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[dict] = []
        self._next_id = 1
        self._load()
        # 初始化子集成
        self._git = GitIntegration(self._config.get("git", {}))
        self._shell = ShellExecutor(self._config.get("shell", {}))
        self._api = ApiCaller(self._config.get("api", {}))

    @classmethod
    def get_instance(cls) -> ExternalManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------- 持久化 ----------------

    def _load(self) -> None:
        try:
            if os.path.exists(_CONFIG_PATH):
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            else:
                self._config = json.loads(json.dumps(_DEFAULT_CONFIG))  # 深拷贝
        except Exception:
            self._config = json.loads(json.dumps(_DEFAULT_CONFIG))
        try:
            if os.path.exists(_APPROVALS_PATH):
                with open(_APPROVALS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._history = list(data.get("history", []))
        except Exception:
            pass

    def _save_config(self) -> None:
        try:
            os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_approvals(self) -> None:
        try:
            os.makedirs(os.path.dirname(_APPROVALS_PATH), exist_ok=True)
            with self._lock:
                data = {"history": list(self._history[-500:])}
            with open(_APPROVALS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception:
            pass

    # ---------------- 配置 ----------------

    def get_config(self) -> dict:
        with self._lock:
            # 不返回密钥实际值
            cfg = json.loads(json.dumps(self._config))
            return cfg

    def update_config(self, section: str, config: dict) -> dict:
        """更新某一节的配置。section = git / shell / api。"""
        if section not in ("git", "shell", "api"):
            return {"ok": False, "error": "unknown section"}
        with self._lock:
            self._config[section] = config
        self._save_config()
        # 重新初始化子集成
        if section == "git":
            self._git.update_config(config)
        elif section == "shell":
            self._shell.update_config(config)
        elif section == "api":
            self._api.update_config(config)
        return {"ok": True}

    def status(self) -> dict:
        return {
            "git": self._git.status(),
            "shell": self._shell.status(),
            "api": self._api.status(),
            "pending_approvals": len(self._pending),
        }

    # ---------------- 子集成访问 ----------------

    @property
    def git(self) -> GitIntegration:
        return self._git

    @property
    def shell(self) -> ShellExecutor:
        return self._shell

    @property
    def api(self) -> ApiCaller:
        return self._api

    # ---------------- 审批 ----------------

    def request_approval(
        self,
        op_type: str,
        agent: Any,
        summary: str,
        detail: dict,
        risk_level: str = RISK_MEDIUM,
    ) -> str:
        """发起一个审批请求。返回审批 ID。"""
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
        req = ApprovalRequest(
            op_type=op_type,
            agent_id=agent_id,
            agent_name=agent_name,
            species=species,
            summary=summary,
            detail=detail,
            risk_level=risk_level,
        )
        with self._lock:
            self._pending[req.id] = req
        return req.id

    def list_pending(self) -> list[dict]:
        with self._lock:
            now = time.time()
            # 自动过期未响应的审批
            expired = []
            for aid, req in list(self._pending.items()):
                if not req.decision and now - req.created_ts > _APPROVAL_TIMEOUT:
                    req.decision = "rejected"
                    req.decided_ts = now
                    req.decision_reason = "审批超时自动拒绝"
                    expired.append(req.to_dict())
            for req_dict in expired:
                self._history.append(req_dict)
                self._pending.pop(req_dict["id"], None)
            if expired:
                self._save_approvals()
            return [r.to_dict() for r in self._pending.values() if not r.decision]

    def decide(self, approval_id: str, decision: str, reason: str = "") -> dict:
        """监工做出审批决定。decision = approved / rejected。"""
        with self._lock:
            req = self._pending.get(approval_id)
        if req is None or req.decision:
            return {"ok": False, "error": "审批不存在或已决定"}
        req.decision = decision
        req.decided_ts = time.time()
        req.decision_reason = reason
        # 如果通过，执行操作
        if decision == "approved":
            req.result = self._execute_approved(req)
        # 移到历史
        with self._lock:
            self._history.append(req.to_dict())
            if len(self._history) > 500:
                self._history = self._history[-500:]
            self._pending.pop(approval_id, None)
        self._save_approvals()
        return {"ok": True, "result": req.result, "decision": decision}

    def list_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._history[-limit:])

    def _execute_approved(self, req: ApprovalRequest) -> dict:
        """审批通过后，执行实际操作。"""
        try:
            if req.op_type == OP_GIT:
                args = req.detail.get("args", [])
                result = self._git.execute(args)
                return result.to_dict()
            elif req.op_type == OP_SHELL:
                command = req.detail.get("command", "")
                result = self._shell.execute(command)
                return result.to_dict()
            elif req.op_type == OP_API:
                result = self._api.call(
                    req.detail.get("endpoint", ""),
                    method=req.detail.get("method", "GET"),
                    path=req.detail.get("path", ""),
                    query=req.detail.get("query"),
                    body=req.detail.get("body"),
                    extra_headers=req.detail.get("headers"),
                )
                return result.to_dict()
            else:
                return {"ok": False, "error": f"unknown op_type: {req.op_type}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 便捷入口 ----------------

    def execute_git(
        self, agent: Any, args: list[str], summary: str = "", risk_level: str = RISK_LOW
    ) -> dict:
        """执行 git 命令。读类操作（status/log）无需审批，写类操作需审批。"""
        if not self._git.enabled:
            return {"ok": False, "error": "Git 集成未启用"}
        subcmd = args[0] if args else ""
        # 读类直接执行
        read_only = subcmd in (
            "status",
            "log",
            "diff",
            "show",
            "branch",
            "rev-parse",
            "remote",
        )
        if read_only and not self._config["git"].get("require_approval", True):
            result = self._git.execute(args)
            return result.to_dict()
        # 写类走审批
        if not summary:
            summary = f"git {' '.join(args)}"
        detail = {"args": args}
        approval_id = self.request_approval(OP_GIT, agent, summary, detail, risk_level)
        return {
            "ok": False,
            "pending_approval": approval_id,
            "summary": summary,
            "message": "等待监工审批",
        }

    def execute_shell(
        self, agent: Any, command: str, summary: str = "", risk_level: str = RISK_MEDIUM
    ) -> dict:
        """执行 shell 命令（始终需要审批）。"""
        if not self._shell.enabled:
            return {"ok": False, "error": "Shell 集成未启用"}
        # 先校验白名单/黑名单
        ok, reason = self._shell.validate(command)
        if not ok:
            return {"ok": False, "error": reason}
        if not summary:
            summary = command[:80]
        detail = {"command": command}
        approval_id = self.request_approval(
            OP_SHELL, agent, summary, detail, risk_level
        )
        return {
            "ok": False,
            "pending_approval": approval_id,
            "summary": summary,
            "message": "等待监工审批",
        }

    def call_api(
        self,
        agent: Any,
        endpoint: str,
        method: str = "GET",
        path: str = "",
        query: dict | None = None,
        body: Any = None,
        summary: str = "",
        risk_level: str = RISK_LOW,
    ) -> dict:
        """调用外部 API。GET 默认低风险，POST/PUT/DELETE 中高风险。"""
        if not self._api.enabled:
            return {"ok": False, "error": "API 集成未启用"}
        if method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
            risk_level = RISK_HIGH if risk_level == RISK_LOW else risk_level
        if not summary:
            summary = f"{method} {endpoint}/{path}"
        detail = {
            "endpoint": endpoint,
            "method": method,
            "path": path,
            "query": query,
            "body": body,
        }
        # GET 类默认放行（不需要审批），其他走审批
        if method.upper() == "GET" and not self._config["api"].get(
            "require_approval", True
        ):
            result = self._api.call(
                endpoint, method=method, path=path, query=query, body=body
            )
            return result.to_dict()
        approval_id = self.request_approval(OP_API, agent, summary, detail, risk_level)
        return {
            "ok": False,
            "pending_approval": approval_id,
            "summary": summary,
            "message": "等待监工审批",
        }


def get_external_manager() -> ExternalManager:
    return ExternalManager.get_instance()
