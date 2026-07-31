"""BlueDeer MCP 工具市场：工具发现、安装、加载。

支持从本地 manifest 或远程 URL 安装工具，自动校验并注入注册表。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

from tools.base_tool import BaseTool
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.tool_market")

# 工具市场本地数据目录
_MARKET_DIR = "tools/market"
_MANIFEST_FILE = os.path.join(_MARKET_DIR, "manifest.json")


@dataclass
class ToolPackage:
    """工具包元数据。"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    source_url: str = ""
    entry_point: str = ""  # 类名
    file_path: str = ""    # 本地安装路径
    category: str = "read"
    tags: list[str] = field(default_factory=list)


class ToolMarket:
    """工具市场：管理第三方工具包的安装、加载、查询。"""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry
        self._packages: dict[str, ToolPackage] = {}
        self._load_manifest()

    @property
    def registry(self) -> ToolRegistry | None:
        return self._registry

    @registry.setter
    def registry(self, reg: ToolRegistry) -> None:
        self._registry = reg

    # ============== 查询 ==============

    def search(self, query: str = "", tags: list[str] | None = None) -> list[ToolPackage]:
        """搜索已安装的工具包。"""
        results = list(self._packages.values()) if not query else []
        if query:
            q = query.lower()
            results = [
                p for p in self._packages.values()
                if q in p.name.lower() or q in p.description.lower() or q in " ".join(p.tags).lower()
            ]
        if tags:
            tag_set = set(t.lower() for t in tags)
            results = [p for p in results if tag_set & set(t.lower() for t in p.tags)]
        return results

    def filter_by_category(self, cat: str) -> list[ToolPackage]:
        return [p for p in self._packages.values() if p.category == cat]

    def get(self, name: str) -> ToolPackage | None:
        return self._packages.get(name)

    def list_installed(self) -> list[ToolPackage]:
        return list(self._packages.values())

    def install_tool(self, tool_id: str, source: str | None = None) -> ToolPackage:
        if tool_id in self._packages:
            raise ValueError(f"工具 {tool_id} 已安装")
        if source:
            return self.install_from_url(source, tool_name=tool_id)
        raise ValueError(f"工具 {tool_id} 未找到且未指定 source")

    def uninstall_tool(self, tool_id: str) -> bool:
        return self.remove(tool_id)

    # ============== 安装 ==============

    def install_from_url(self, url: str, tool_name: str | None = None) -> ToolPackage:
        """从 URL 安装工具包。

        支持：
        - https://raw.githubusercontent.com/.../tool.py 直接 Python 文件
        - https://github.com/.../releases/download/.../package.json manifest

        Args:
            url: 工具包下载 URL。
            tool_name: 工具名（自动推断时可省略）。

        Returns:
            安装后的 ToolPackage。

        Raises:
            ValueError: URL 无效或下载失败。
            ImportError: 工具类验证失败。
        """
        import urllib.request
        import tempfile

        logger.info("正在从 %s 安装工具...", url)

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            raise ValueError(f"下载失败: {e}") from e

        # 推断工具名
        name = tool_name or self._infer_name(url, content)

        # 写入本地文件
        os.makedirs(_MARKET_DIR, exist_ok=True)
        file_path = os.path.join(_MARKET_DIR, f"{name}.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 验证并提取元数据
        tool_cls = self._validate_tool(file_path, name)
        try:
            _inst = tool_cls()
            _cat = _inst.category.value if hasattr(_inst, "category") else "read"
        except Exception:
            _cat = "read"
        pkg = ToolPackage(
            name=name,
            version="0.1.0",
            description=getattr(tool_cls, "__doc__", "") or f"从 {url} 安装的工具",
            source_url=url,
            entry_point=tool_cls.__name__,
            file_path=file_path,
            category=_cat,
            tags=["community"],
        )

        self._packages[name] = pkg
        self._save_manifest()

        # 自动注册
        if self._registry is not None:
            instance = tool_cls()
            self._registry.register(instance)
            logger.info("工具 %s 已自动注册", name)

        logger.info("工具 %s v%s 安装成功", name, pkg.version)
        return pkg

    def install_local(self, file_path: str, tool_name: str | None = None) -> ToolPackage:
        """从本地 Python 文件安装工具。

        Args:
            file_path: 本地 .py 文件路径。
            tool_name: 工具名。

        Returns:
            安装后的 ToolPackage。
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        name = tool_name or os.path.splitext(os.path.basename(file_path))[0]
        tool_cls = self._validate_tool(file_path, name)

        # 复制到市场目录
        os.makedirs(_MARKET_DIR, exist_ok=True)
        dst = os.path.join(_MARKET_DIR, f"{name}.py")
        import shutil
        shutil.copy2(file_path, dst)

        try:
            _inst = tool_cls()
            _cat = _inst.category.value if hasattr(_inst, "category") else "read"
        except Exception:
            _cat = "read"
        pkg = ToolPackage(
            name=name,
            version="0.1.0",
            description=getattr(tool_cls, "__doc__", "") or f"本地工具 {name}",
            source_url=file_path,
            entry_point=tool_cls.__name__,
            file_path=dst,
            category=_cat,
            tags=["local"],
        )

        self._packages[name] = pkg
        self._save_manifest()

        if self._registry is not None:
            instance = tool_cls()
            self._registry.register(instance)

        logger.info("本地工具 %s 安装成功", name)
        return pkg

    def remove(self, name: str) -> bool:
        """卸载工具包。"""
        pkg = self._packages.pop(name, None)
        if pkg is None:
            return False
        if os.path.exists(pkg.file_path):
            os.remove(pkg.file_path)
        self._save_manifest()
        logger.info("工具 %s 已卸载", name)
        return True

    # ============== 内部 ==============

    def _infer_name(self, url: str, content: str) -> str:
        """从 URL 或内容推断工具名。"""
        # 从文件名推断
        basename = os.path.splitext(os.path.basename(url.split("?")[0]))[0]
        if basename and basename != "tool" and basename != "default":
            return basename
        # 从类名推断（找 BaseTool 子类）
        import re
        match = re.search(r"class\s+(\w+)\s*\(.*BaseTool", content)
        if match:
            cls_name = match.group(1)
            return cls_name[0].lower() + cls_name[1:]  # camelCase → camelCase
        return "community_tool"

    def _validate_tool(self, file_path: str, name: str) -> type[BaseTool]:
        """验证 Python 文件包含有效的 BaseTool 子类。"""
        spec = importlib.util.spec_from_file_location(f"_market_{name}", file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载 {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # 找 BaseTool 子类
        tool_cls = None
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and issubclass(obj, BaseTool) and obj is not BaseTool:
                tool_cls = obj
                break

        if tool_cls is None:
            raise ImportError(f"{file_path} 中未找到 BaseTool 子类")

        # 验证必要属性
        instance = tool_cls()
        if not instance.name or not instance.category:
            raise ImportError(f"工具类 {tool_cls.__name__} 缺少 name 或 category")

        logger.info("工具验证通过: %s → %s", tool_cls.__name__, instance.name)
        return tool_cls

    def _load_manifest(self) -> None:
        """从磁盘加载 manifest。"""
        if not os.path.exists(_MANIFEST_FILE):
            self._packages = {}
            return
        try:
            with open(_MANIFEST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._packages = {
                name: ToolPackage(**pkg_data)
                for name, pkg_data in data.items()
            }
        except Exception as e:
            logger.warning("加载工具 manifest 失败: %s", e)
            self._packages = {}

    def _save_manifest(self) -> None:
        """保存 manifest 到磁盘。"""
        os.makedirs(_MARKET_DIR, exist_ok=True)
        data = {
            name: asdict(pkg)
            for name, pkg in self._packages.items()
        }
        with open(_MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
