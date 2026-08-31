"""远程 Plugin 仓库：搜索、从 Git URL 安装。

支持从 GitHub / GitLab 等公开仓库自动 clone 或下载 zip 安装插件。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger("bluedeer.plugin_repo")

_PLUGIN_DIR = "plugins"
_REPO_CACHE = "data/plugin_repo_cache.json"
_GITHUB_API = "https://api.github.com"


@dataclass
class RemotePluginInfo:
    name: str
    version: str
    description: str
    author: str
    source_url: str
    source_type: str
    installed: bool = False


@dataclass
class PluginRepoResult:
    plugins: list[RemotePluginInfo] = field(default_factory=list)
    total: int = 0
    error: str = ""


from functools import lru_cache


class PluginRepo:
    def __init__(self, plugin_dir: str = _PLUGIN_DIR) -> None:
        self._plugin_dir = plugin_dir
        self._cache: dict[str, Any] = self._load_cache()

    def _load_cache(self) -> dict[str, Any]:
        try:
            if os.path.exists(_REPO_CACHE):
                with open(_REPO_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning("加载插件仓库缓存失败: %s", e)
        return {"plugins": [], "updated_at": 0}

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(_REPO_CACHE), exist_ok=True)
            with open(_REPO_CACHE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存插件仓库缓存失败: %s", e)

    def _get_installed(self) -> set[str]:
        pdir = Path(self._plugin_dir)
        if not pdir.is_dir():
            return set()
        installed: set[str] = set()
        for entry in pdir.iterdir():
            if entry.is_dir() and (entry / "__init__.py").is_file():
                installed.add(entry.name)
            elif entry.is_file() and entry.suffix == ".py" and entry.stem != "__init__":
                installed.add(entry.stem)
        return installed

    def _parse_gh_url(self, url: str) -> tuple[str, str, str] | None:
        m = re.match(
            r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?$", url
        )
        if m:
            return m.group(1), m.group(2), m.group(3) or "main"
        m2 = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m2:
            return m2.group(1), m2.group(2), "main"
        return None

    def _parse_gitlab_url(self, url: str) -> tuple[str, str, str] | None:
        m = re.match(
            r"https?://gitlab\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/-/tree/([^/]+))?$", url
        )
        if m:
            return m.group(1), m.group(2), m.group(3) or "main"
        return None

    def search_github(
        self,
        query: str = "",
        max_results: int = 20,
    ) -> PluginRepoResult:
        installed = self._get_installed()
        plugins: list[RemotePluginInfo] = []

        if not query:
            url = f"{_GITHUB_API}/search/repositories?q=bluedeer-plugin+in:name,description&sort=updated&per_page={max_results}"
        else:
            url = f"{_GITHUB_API}/search/repositories?q={urllib.parse.quote(query)}+in:name,description&sort=stars&per_page={max_results}"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "BlueDeer/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("items", []):
                    full_name = item.get("full_name", "")
                    pm = PluginRepo._parse_manifest_from_gh(item)
                    plugins.append(
                        RemotePluginInfo(
                            name=pm["name"] or item["name"],
                            version=pm.get("version", "0.1.0"),
                            description=pm.get("description")
                            or item.get("description", ""),
                            author=item.get("owner", {}).get("login", ""),
                            source_url=item.get("clone_url", ""),
                            source_type="github",
                            installed=full_name.replace("/", ".") in installed
                            or item["name"] in installed,
                        )
                    )
        except Exception as e:
            return PluginRepoResult(error=f"GitHub 搜索失败: {e}")

        return PluginRepoResult(plugins=plugins, total=len(plugins))

    @staticmethod
    def _parse_manifest_from_gh(item: dict) -> dict:
        topic_names = (
            [t.get("name", "") for t in item.get("topics", [])]
            if item.get("topics")
            else []
        )
        desc = item.get("description", "")
        name = ""
        for t in topic_names:
            if t.startswith("plugin-"):
                name = t.replace("plugin-", "", 1)
        if not name:
            name = item.get("name", "")
        return {
            "name": name,
            "version": "0.1.0",
            "description": desc,
        }

    def install_from_git(
        self,
        url: str,
        branch: str = "main",
        target_name: str = "",
    ) -> tuple[bool, str]:
        try:
            if not shutil.which("git"):
                return False, "系统未安装 git，请先安装 Git CLI"

            parsed = self._parse_gh_url(url)
            if not parsed:
                parsed = self._parse_gitlab_url(url)
            if not parsed:
                return False, f"不支持的 Git URL: {url}（仅支持 GitHub / GitLab）"

            owner, repo, ref = parsed
            clone_url = f"https://github.com/{owner}/{repo}.git"
            plugin_name = target_name or repo.lower().replace("-", "_").replace(
                ".", "_"
            )

            target_dir = Path(self._plugin_dir) / plugin_name
            if target_dir.exists():
                return False, f"插件 {plugin_name} 已存在于 {target_dir}，请先卸载"

            os.makedirs(self._plugin_dir, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", "-b", ref, clone_url, str(tmpdir)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    return False, f"Git clone 失败: {result.stderr.strip()[:300]}"

                src_plugin_dir = Path(tmpdir)
                init_py = src_plugin_dir / "__init__.py"
                if not init_py.exists():
                    py_files = list(src_plugin_dir.glob("*.py"))
                    py_dirs = [
                        d
                        for d in src_plugin_dir.iterdir()
                        if d.is_dir() and (d / "__init__.py").exists()
                    ]
                    if py_dirs:
                        src_plugin_dir = py_dirs[0]
                    elif py_files:
                        shutil.copy2(py_files[0], target_dir)
                        return True, f"已从 {url} 安装单文件插件 → {target_dir}"
                    else:
                        return False, "仓库中未找到有效的插件文件"

                shutil.copytree(src_plugin_dir, target_dir, dirs_exist_ok=True)

            logger.info("插件 %s 已从 %s 安装", plugin_name, url)
            return True, f"✅ 插件 {plugin_name} 已从 {url} 安装到 {target_dir}"

        except subprocess.TimeoutExpired:
            return False, "Git clone 超时（超过 120s）"
        except Exception as e:
            return False, f"安装失败: {e}"

    def install_from_zip(
        self,
        zip_url: str,
        target_name: str = "",
    ) -> tuple[bool, str]:
        try:
            plugin_name = target_name or os.path.splitext(os.path.basename(zip_url))[0]
            target_dir = Path(self._plugin_dir) / plugin_name
            if target_dir.exists():
                return False, f"插件 {plugin_name} 已存在"

            os.makedirs(self._plugin_dir, exist_ok=True)
            zip_path = os.path.join(
                tempfile.gettempdir(), f"bd_plugin_{int(time.time())}.zip"
            )
            try:
                urllib.request.urlretrieve(zip_url, zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(target_dir)
            finally:
                if os.path.exists(zip_path):
                    os.unlink(zip_path)

            logger.info("插件 %s 已从 %s 安装", plugin_name, zip_url)
            return True, f"✅ 插件 {plugin_name} 已安装到 {target_dir}"
        except Exception as e:
            return False, f"ZIP 安装失败: {e}"

    def uninstall(self, name: str) -> tuple[bool, str]:
        target = Path(self._plugin_dir) / name
        if not target.exists():
            return False, f"插件 {name} 未安装"
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                os.unlink(target)
            return True, f"✅ 插件 {name} 已卸载"
        except Exception as e:
            return False, f"卸载失败: {e}"

    _PLUGIN_DEPS: ClassVar[dict[str, list[str]]] = {
        # 插件名称 -> 依赖的插件名称列表
    }

    @staticmethod
    def register_deps(plugin: str, deps: list[str]) -> None:
        PluginRepo._PLUGIN_DEPS[plugin] = deps

    def _has_circular(self, name: str, path: set[str] | None = None) -> bool:
        """递归检测 circular dependency。"""
        if path is None:
            path = set()
        if name in path:
            return True
        path.add(name)
        for dep in self._PLUGIN_DEPS.get(name, []):
            if self._has_circular(dep, path):
                return True
        path.discard(name)
        return False

    def resolve_deps(self, plugin_name: str) -> list[str]:
        """返回有序安装列表（拓扑序），含 circular 检测。
        Args:
            plugin_name: 插件名。
        Returns:
            从依赖到自身的安装顺序列表。
        Raises:
            ValueError: 存在循环依赖。
        """
        if self._has_circular(plugin_name):
            raise ValueError(f"插件 {plugin_name} 存在循环依赖")
        visited: set[str] = set()
        order: list[str] = []

        def dfs(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            for dep in self._PLUGIN_DEPS.get(name, []):
                dfs(dep)
            order.append(name)

        dfs(plugin_name)
        return order

    @lru_cache(maxsize=32)  # noqa: B019
    def cached_search(self, query: str) -> PluginRepoResult:
        """带 LRU 缓存的搜索（缓存最近 32 个查询）。"""
        return self.search_github(query)

    def refresh_cache(self) -> None:
        self._cache = {"plugins": [], "updated_at": time.time()}
        self._save_cache()
