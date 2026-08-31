"""BlueDeer 统一异常体系。

所有模块的自定义异常继承此层次结构，便于上层统一捕获和处理。
每个异常携带 code（数字错误码）和 message（描述）。
使用方式：
    from core.exceptions import ConfigError
    raise ConfigError(code=4001, message="配置缺失")
"""

from __future__ import annotations


class BlueDeerError(Exception):
    """BlueDeer 基础异常，所有自定义异常的基类。"""

    def __init__(self, code: int = 0, message: str = "", *args) -> None:
        self.code = code
        self.message = message or self.__class__.__doc__ or ""
        super().__init__(f"[{self.code}] {self.message}", *args)


class ConfigError(BlueDeerError):
    """配置错误：配置缺失、类型错误、验证失败等。"""


class DatabaseError(BlueDeerError):
    """数据库操作错误。"""


class NetworkError(BlueDeerError):
    """网络通信错误。"""


class ValidationError(BlueDeerError):
    """数据校验错误。"""


class PluginError(BlueDeerError):
    """插件相关错误。"""


class AuthError(BlueDeerError):
    """认证/授权错误。"""


class TimeoutError(BlueDeerError):
    """操作超时错误。"""


class ResourceNotFound(BlueDeerError):
    """资源未找到。"""


# ── 保留原有兼容别名 ──


class ConfigurationError(ConfigError):
    """（兼容）配置错误。"""


class TaskError(BlueDeerError):
    """任务相关错误基类。"""


class TaskNotFoundError(TaskError, ResourceNotFound):
    """任务未找到。"""


class TaskTimeoutError(TaskError, TimeoutError):
    """任务超时。"""


class TaskExecutionError(TaskError):
    """任务执行失败。"""


class TaskDependencyError(TaskError):
    """任务依赖未满足。"""


class TaskBlockedError(TaskError):
    """任务因上游失败被阻塞。"""


class ScheduleError(BlueDeerError):
    """调度相关错误基类。"""


class ScheduleNotFoundError(ScheduleError, ResourceNotFound):
    """定时任务未找到。"""


class WebhookError(BlueDeerError):
    """Webhook 相关错误基类。"""


class WebhookNotFoundError(WebhookError, ResourceNotFound):
    """Webhook 未找到。"""


class AgentError(BlueDeerError):
    """Agent 相关错误基类。"""


class AgentNotFoundError(AgentError, ResourceNotFound):
    """Agent 未找到。"""


class ModelError(BlueDeerError):
    """模型调用相关错误基类。"""


class ModelRoutingError(ModelError):
    """模型路由失败。"""


class ModelDegradedError(ModelError):
    """模型已降级。"""


class ToolError(BlueDeerError):
    """工具相关错误基类。"""


class ToolNotFoundError(ToolError, ResourceNotFound):
    """工具未注册。"""


class ToolValidationError(ToolError, ValidationError):
    """工具参数校验失败。"""


class ToolExecutionError(ToolError):
    """工具执行失败（重试耗尽）。"""


class ToolCircuitBreakerError(ToolError):
    """工具熔断。"""


class StorageError(BlueDeerError):
    """存储相关错误基类。"""


class StorageConnectionError(StorageError, DatabaseError):
    """数据库连接失败。"""


class StorageQueryError(StorageError):
    """查询执行失败。"""


class RAGError(BlueDeerError):
    """RAG 检索相关错误基类。"""


class SecurityError(BlueDeerError):
    """安全风控相关错误基类。"""


class CapabilityViolation(SecurityError):
    """Agent 不具备所需能力。"""


class PermissionDeniedError(SecurityError, AuthError):
    """权限不足。"""


class PluginNotFoundError(PluginError, ResourceNotFound):
    """插件未找到。"""


class PluginLoadError(PluginError):
    """插件加载失败。"""
