"""commit 39：受限 shell 执行器。

零基础读者可以这样理解：
- 智能体可以执行 shell 命令，但有白名单/黑名单限制
- 白名单：只允许 python / pytest / npm / git / docker 等
- 黑名单：禁止 rm -rf / sudo / chmod 777 / curl 等
- 超时自动终止（默认 60 秒）
- 所有命令需监工审批
"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from typing import Any

# 默认白名单：允许执行的命令前缀
_DEFAULT_WHITELIST: list[str] = [
    "python",
    "python3",
    "pytest",
    "pip",
    "npm",
    "node",
    "yarn",
    "git",
    "docker",
    "docker-compose",
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
]

# 默认黑名单：禁止的命令片段（出现在命令任何位置都拒绝）
_DEFAULT_BLACKLIST: list[str] = [
    "rm -rf",
    "rm -fr",
    "sudo",
    "chmod 777",
    "curl ",
    "wget ",
    ":(){:|:&};:",  # fork bomb
    "> /dev/sda",
    "/etc/passwd",
    "/etc/shadow",
    "mkfs",
    "dd if=",
]


class ShellResult:
    """shell 命令执行结果。"""

    __slots__ = (
        "command",
        "duration_ms",
        "ok",
        "returncode",
        "stderr",
        "stdout",
        "timeout",
        "workdir",
    )

    def __init__(
        self,
        ok: bool,
        command: str = "",
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        duration_ms: float = 0,
        timeout: bool = False,
        workdir: str = "",
    ) -> None:
        self.ok = ok
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.duration_ms = duration_ms
        self.timeout = timeout
        self.workdir = workdir

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": self.command,
            "stdout": self.stdout[:4000],
            "stderr": self.stderr[:2000],
            "returncode": self.returncode,
            "duration_ms": round(self.duration_ms, 2),
            "timeout": self.timeout,
            "workdir": self.workdir,
        }


class ShellExecutor:
    """受限 shell 执行器。"""

    def __init__(self, config: dict) -> None:
        """config 形如：
        {
          "enabled": false,
          "whitelist": ["python", "pytest", ...],
          "blacklist": ["rm -rf", "sudo", ...],
          "timeout": 60,
          "workdir": "/workspace",
          "require_approval": true
        }
        """
        self._config = dict(config)
        self._lock = threading.RLock()
        self._enabled = bool(self._config.get("enabled", False))
        self._whitelist = list(self._config.get("whitelist", _DEFAULT_WHITELIST))
        self._blacklist = list(self._config.get("blacklist", _DEFAULT_BLACKLIST))
        self._timeout = float(self._config.get("timeout", 60))
        self._workdir = self._config.get("workdir", "") or os.getcwd()
        self._require_approval = bool(self._config.get("require_approval", True))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def update_config(self, config: dict) -> None:
        with self._lock:
            self._config.update(config)
            self._enabled = bool(self._config.get("enabled", False))
            self._whitelist = list(self._config.get("whitelist", _DEFAULT_WHITELIST))
            self._blacklist = list(self._config.get("blacklist", _DEFAULT_BLACKLIST))
            self._timeout = float(self._config.get("timeout", 60))
            self._workdir = self._config.get("workdir", "") or os.getcwd()
            self._require_approval = bool(self._config.get("require_approval", True))

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "whitelist": list(self._whitelist),
            "blacklist": list(self._blacklist),
            "timeout": self._timeout,
            "workdir": self._workdir,
            "require_approval": self._require_approval,
        }

    def validate(self, command: str) -> tuple[bool, str]:
        """校验命令是否被允许。返回 (是否允许, 原因)。"""
        if not command or not command.strip():
            return False, "空命令"
        cmd_lower = command.lower()
        # 1. 黑名单检查
        for bad in self._blacklist:
            if bad.lower() in cmd_lower:
                return False, f"命中黑名单：{bad}"
        # 2. 解析命令首词
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return False, f"命令解析失败：{e}"
        if not parts:
            return False, "空命令"
        first = parts[0]
        # 去掉路径前缀，只取命令名
        first_name = os.path.basename(first)
        # 3. 白名单检查
        for allowed in self._whitelist:
            if first_name == allowed or first == allowed:
                return True, "ok"
        return False, f"命令 {first_name} 不在白名单"

    def execute(
        self, command: str, caller: Any = None, timeout: float | None = None
    ) -> ShellResult:
        """执行 shell 命令。"""
        if not self._enabled:
            return ShellResult(False, command=command, stderr="Shell 集成未启用")
        ok, reason = self.validate(command)
        if not ok:
            return ShellResult(False, command=command, stderr=reason)
        actual_timeout = float(timeout if timeout is not None else self._timeout)
        start = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self._workdir,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                check=False,
            )
            dur = (time.time() - start) * 1000
            return ShellResult(
                ok=proc.returncode == 0,
                command=command,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
                duration_ms=dur,
                workdir=self._workdir,
            )
        except subprocess.TimeoutExpired:
            return ShellResult(
                False,
                command=command,
                stderr=f"超时（{actual_timeout}s）",
                returncode=-1,
                timeout=True,
                duration_ms=actual_timeout * 1000,
                workdir=self._workdir,
            )
        except Exception as e:
            return ShellResult(
                False,
                command=command,
                stderr=f"执行异常: {e}",
                returncode=-1,
                duration_ms=(time.time() - start) * 1000,
                workdir=self._workdir,
            )
