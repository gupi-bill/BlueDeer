"""commit 39：外部集成子包。

零基础读者可以这样理解：让智能体能"伸出手"操作真实世界——
- git_integration：执行真实的 git 命令
- shell_executor：执行受限的 shell 命令
- api_caller：调用外部 HTTP API
- external_manager：统一管理开关、审批、配置
"""

from core.digital_life.external.api_caller import ApiCaller
from core.digital_life.external.external_manager import (
    ExternalManager,
    get_external_manager,
)
from core.digital_life.external.git_integration import GitIntegration
from core.digital_life.external.shell_executor import ShellExecutor

__all__ = [
    "ApiCaller",
    "ExternalManager",
    "GitIntegration",
    "ShellExecutor",
    "get_external_manager",
]
