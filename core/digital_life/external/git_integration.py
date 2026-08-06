"""commit 39：真实 Git 集成（用 subprocess 调 git 命令，零第三方依赖）。

零基础读者可以这样理解：
- 海狸可以执行真实的 git status / commit / push 等命令
- 命令在指定仓库目录下执行
- 所有操作都走 ExternalManager 审批
- 输出和耗时都记录
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Any

# 允许的 git 子命令白名单
_GIT_WHITELIST: set[str] = {
    "status",
    "add",
    "commit",
    "push",
    "pull",
    "fetch",
    "branch",
    "checkout",
    "merge",
    "log",
    "diff",
    "show",
    "stash",
    "tag",
    "remote",
    "rev-parse",
    "config",
}

# 危险子命令（默认拒绝，需用户在配置中显式允许）
_GIT_DANGEROUS: set[str] = {
    "reset",
    "clean",
    "force-push",
    "rebase",
}


class GitResult:
    """git 命令执行结果。"""

    __slots__ = (
        "command",
        "duration_ms",
        "ok",
        "repo_path",
        "returncode",
        "stderr",
        "stdout",
    )

    def __init__(
        self,
        ok: bool,
        command: str = "",
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        duration_ms: float = 0,
        repo_path: str = "",
    ) -> None:
        self.ok = ok
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.duration_ms = duration_ms
        self.repo_path = repo_path

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": self.command,
            "stdout": self.stdout[:4000],
            "stderr": self.stderr[:2000],
            "returncode": self.returncode,
            "duration_ms": round(self.duration_ms, 2),
            "repo_path": self.repo_path,
        }


class GitIntegration:
    """真实 Git 集成。每个 ExternalManager 实例持有一个。"""

    def __init__(self, config: dict) -> None:
        """config 形如：
        {
          "enabled": false,
          "repo_path": "/path/to/repo",
          "auto_commit": false,
          "require_approval": true,
          "allow_dangerous": false
        }
        """
        self._config = dict(config)
        self._lock = threading.RLock()
        self._repo_path = self._config.get("repo_path", "")
        self._enabled = bool(self._config.get("enabled", False))
        self._require_approval = bool(self._config.get("require_approval", True))
        self._allow_dangerous = bool(self._config.get("allow_dangerous", False))

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def repo_path(self) -> str:
        return self._repo_path

    def update_config(self, config: dict) -> None:
        with self._lock:
            self._config.update(config)
            self._repo_path = self._config.get("repo_path", "")
            self._enabled = bool(self._config.get("enabled", False))
            self._require_approval = bool(self._config.get("require_approval", True))
            self._allow_dangerous = bool(self._config.get("allow_dangerous", False))

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "repo_path": self._repo_path,
            "require_approval": self._require_approval,
            "allow_dangerous": self._allow_dangerous,
            "repo_exists": bool(
                self._repo_path
                and os.path.isdir(self._repo_path)
                and os.path.isdir(os.path.join(self._repo_path, ".git"))
            ),
        }

    def execute(
        self, args: list[str], caller: Any = None, timeout: float = 30.0
    ) -> GitResult:
        """执行 git 命令。args 是 ["status"] / ["add", "."] / ["commit", "-m", "xxx"] 等。

        Args:
            args: git 子命令及参数列表
            caller: 调用方智能体（用于审批上下文）
            timeout: 超时秒数
        """
        if not self._enabled:
            return GitResult(
                False, command="git " + " ".join(args), stderr="Git 集成未启用"
            )
        if not args:
            return GitResult(False, stderr="空命令")
        subcmd = args[0]
        if subcmd not in _GIT_WHITELIST:
            if subcmd in _GIT_DANGEROUS and self._allow_dangerous:
                pass  # 危险命令但用户显式允许
            else:
                return GitResult(
                    False, command=f"git {subcmd}", stderr=f"子命令 {subcmd} 不在白名单"
                )
        if not self._repo_path or not os.path.isdir(self._repo_path):
            return GitResult(
                False, command="git " + " ".join(args), stderr="仓库路径未配置或不存在"
            )
        # 拼完整命令
        full_cmd = ["git"] + list(args)
        start = time.time()
        try:
            proc = subprocess.run(
                full_cmd,
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            dur = (time.time() - start) * 1000
            ok = proc.returncode == 0
            return GitResult(
                ok=ok,
                command=" ".join(full_cmd),
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
                duration_ms=dur,
                repo_path=self._repo_path,
            )
        except subprocess.TimeoutExpired:
            return GitResult(
                False,
                command=" ".join(full_cmd),
                stderr=f"超时（{timeout}s）",
                returncode=-1,
                duration_ms=timeout * 1000,
                repo_path=self._repo_path,
            )
        except Exception as e:
            return GitResult(
                False,
                command=" ".join(full_cmd),
                stderr=f"执行异常: {e}",
                returncode=-1,
                duration_ms=(time.time() - start) * 1000,
                repo_path=self._repo_path,
            )

    # ---------------- 便捷方法 ----------------

    def get_status(self) -> GitResult:
        return self.execute(["status", "--short"])

    def get_log(self, count: int = 10) -> GitResult:
        return self.execute(["log", f"-n{count}", "--oneline"])

    def get_branch(self) -> GitResult:
        return self.execute(["rev-parse", "--abbrev-ref", "HEAD"])

    def commit_all(self, message: str) -> GitResult:
        """add . + commit。"""
        add_res = self.execute(["add", "."])
        if not add_res.ok:
            return add_res
        return self.execute(["commit", "-m", message])

    def push(self, remote: str = "origin", branch: str = "") -> GitResult:
        args = ["push", remote]
        if branch:
            args.append(branch)
        return self.execute(args)
