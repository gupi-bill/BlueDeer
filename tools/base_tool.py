"""BlueDeer 工具基类：统一工具接口与分级。

P1 扩容（A 级）：3 级 → 8 级权限
0. READ             - 只读查询（无副作用）
1. FILE_CREATE      - 文件新建
2. FILE_MODIFY      - 文件修改（MUTATE 为其别名，向后兼容）
3. FILE_DELETE      - 文件删除
4. DB_READWRITE     - 数据库读写
5. NETWORK_REQUEST  - 网络请求
6. SYSTEM_TERMINAL  - 系统终端
7. HAZARDOUS        - 高危格式化（强制前置安全校验）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.capability import Capability


@dataclass
class ToolDef:
    name: str
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    returns: dict[str, Any] = field(default_factory=dict)
    category: str = "read"
    level: int = 0


def validate_input(params: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, rules in schema.items():
        required = rules.get("required", False)
        if required and key not in params:
            errors.append(f"缺少必填参数: {key}")
            continue
        if key not in params:
            continue
        val = params[key]
        expected_type = rules.get("type")
        if expected_type:
            type_map = {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}
            py_type = type_map.get(expected_type)
            if py_type and not isinstance(val, py_type):
                errors.append(f"参数 '{key}' 应为 {expected_type}，实际为 {type(val).__name__}")
        min_val = rules.get("min")
        if min_val is not None and isinstance(val, (int, float)) and val < min_val:
            errors.append(f"参数 '{key}' 不能小于 {min_val}")
        max_val = rules.get("max")
        if max_val is not None and isinstance(val, (int, float)) and val > max_val:
            errors.append(f"参数 '{key}' 不能大于 {max_val}")
    return errors


class ToolCategory(Enum):
    """工具安全分级（P1 扩容：8 级）。

    按危险度递增排序。MUTATE 是 FILE_MODIFY 的别名（向后兼容老代码）。
    """
    READ = "read"                       # 0 只读查询
    FILE_CREATE = "file_create"         # 1 文件新建
    FILE_MODIFY = "file_modify"         # 2 文件修改
    MUTATE = "file_modify"              # 2 别名（兼容老代码）
    FILE_DELETE = "file_delete"         # 3 文件删除
    DB_READWRITE = "db_readwrite"       # 4 数据库读写
    NETWORK_REQUEST = "network_req"     # 5 网络请求
    SYSTEM_TERMINAL = "sys_terminal"    # 6 系统终端
    HAZARDOUS = "hazardous"             # 7 高危格式化


# 权限等级映射（数值越大危险度越高）
_CATEGORY_LEVEL: dict[ToolCategory, int] = {
    ToolCategory.READ: 0,
    ToolCategory.FILE_CREATE: 1,
    ToolCategory.FILE_MODIFY: 2,
    ToolCategory.MUTATE: 2,  # 别名同级
    ToolCategory.FILE_DELETE: 3,
    ToolCategory.DB_READWRITE: 4,
    ToolCategory.NETWORK_REQUEST: 5,
    ToolCategory.SYSTEM_TERMINAL: 6,
    ToolCategory.HAZARDOUS: 7,
}

# 需要前置安全校验的最低等级（NETWORK_REQUEST 及以上）
_SECURITY_CHECK_THRESHOLD = 5


def category_level(category: ToolCategory) -> int:
    """P1 扩容：取工具类别的危险等级（0-7）。"""
    return _CATEGORY_LEVEL.get(category, 0)


def needs_security_check(category: ToolCategory) -> bool:
    """P1 扩容：该类别是否需要前置安全校验。

    NETWORK_REQUEST / SYSTEM_TERMINAL / HAZARDOUS 三级需要校验。
    """
    return category_level(category) >= _SECURITY_CHECK_THRESHOLD


# ToolCategory → 能力名称映射（供 BaseTool.required_capability 默认使用）
_CATEGORY_CAPABILITY_MAP: dict[ToolCategory, str | None] = {
    ToolCategory.READ: "file.read",
    ToolCategory.FILE_CREATE: "file.create",
    ToolCategory.FILE_MODIFY: "file.modify",
    ToolCategory.MUTATE: "file.modify",
    ToolCategory.FILE_DELETE: "file.delete",
    ToolCategory.DB_READWRITE: "db.readwrite",
    ToolCategory.NETWORK_REQUEST: "network.http",
    ToolCategory.SYSTEM_TERMINAL: "system.shell",
    ToolCategory.HAZARDOUS: "system.shell",
}


class BaseTool(ABC):
    """工具抽象基类。

    所有工具需继承此类并实现 execute 方法。
    工具按 ToolCategory 分级（8 级），高危工具由 ToolRegistry 强制前置安全校验。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（唯一标识）。"""

    @property
    @abstractmethod
    def category(self) -> ToolCategory:
        """工具安全分级。"""

    @property
    def required_capability(self) -> str | None:
        """此工具所需的能力名称。子类可覆盖。

        默认按 ToolCategory 映射（见 _CATEGORY_CAPABILITY_MAP）。
        返回 None 表示不需要能力检查（向后兼容）。
        """
        return _CATEGORY_CAPABILITY_MAP.get(self.category)

    def get_tool_info(self) -> ToolDef:
        return ToolDef(
            name=self.name,
            description=self.__class__.__doc__ or "",
            category=self.category.value,
            level=category_level(self.category),
        )

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> Any:
        """执行工具。

        Args:
            params: 工具参数。

        Returns:
            执行结果。
        """
