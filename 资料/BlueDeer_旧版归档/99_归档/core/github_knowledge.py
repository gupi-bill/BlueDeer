"""BlueDeer GitHub 知识融合：实用项目索引与最佳实践提取。

自动索引 GitHub 实用项目，提取最佳实践和代码模板，
融入到森林公司的知识库中。
"""

from __future__ import annotations

import fnmatch
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from core.library import Library, LibraryScope

logger = logging.getLogger("bluedeer.github")


class ProjectCategory(Enum):
    """项目分类。"""

    FRAMEWORK = "framework"  # 框架
    TOOL = "tool"  # 工具
    LIBRARY = "library"  # 库
    BEST_PRACTICE = "best_practice"  # 最佳实践
    TEMPLATE = "template"  # 模板
    ARCHITECTURE = "architecture"  # 架构模式
    ALGORITHM = "algorithm"  # 算法/数据结构


@dataclass
class GitHubProject:
    """GitHub 项目条目。"""

    name: str
    url: str
    description: str
    category: ProjectCategory
    tags: list[str] = field(default_factory=list)
    stars: int = 0
    language: str = ""
    key_insights: list[str] = field(default_factory=list)  # 提取的关键洞见
    indexed_at: float = field(default_factory=time.time)


class GitHubKnowledge:
    """GitHub 知识融合引擎。

    管理实用项目索引，提取最佳实践，融入知识库。
    """

    # 内置的精选实用项目（按分类组织）
    _BUILTIN_PROJECTS: ClassVar[list[dict[str, Any]]] = [
        # ---- 框架类 ----
        {
            "name": "FastAPI",
            "url": "https://github.com/fastapi/fastapi",
            "description": "现代高性能 Python Web 框架，自动 OpenAPI 文档",
            "category": "framework",
            "tags": ["web", "api", "async", "python"],
            "key_insights": ["依赖注入模式", "自动 API 文档生成", "Pydantic 数据验证"],
        },
        {
            "name": "LangChain",
            "url": "https://github.com/langchain-ai/langchain",
            "description": "构建 LLM 应用的框架，支持链式调用和工具集成",
            "category": "framework",
            "tags": ["llm", "ai", "chain", "agent"],
            "key_insights": ["链式调用模式", "Agent 工具集成", "Prompt 模板管理"],
        },
        {
            "name": "CrewAI",
            "url": "https://github.com/joaomdmoura/crewAI",
            "description": "多 Agent 协作框架，角色分工与任务路由",
            "category": "framework",
            "tags": ["multi-agent", "collaboration", "ai"],
            "key_insights": ["角色分工模式", "任务委派", "Agent 间通信"],
        },
        {
            "name": "AutoGen",
            "url": "https://github.com/microsoft/autogen",
            "description": "微软多 Agent 对话框架，支持多轮对话与代码执行",
            "category": "framework",
            "tags": ["multi-agent", "conversation", "microsoft"],
            "key_insights": ["多 Agent 对话模式", "代码执行沙箱", "对话管理"],
        },
        {
            "name": "Pydantic",
            "url": "https://github.com/pydantic/pydantic",
            "description": "Python 数据验证库，类型安全的数据模型",
            "category": "framework",
            "tags": ["validation", "types", "python"],
            "key_insights": ["数据验证模式", "类型安全", "JSON Schema 生成"],
        },
        # ---- 工具类 ----
        {
            "name": "Redis",
            "url": "https://github.com/redis/redis",
            "description": "内存数据结构存储，支持缓存、消息队列、发布订阅",
            "category": "tool",
            "tags": ["cache", "database", "message-queue"],
            "key_insights": ["LRU 缓存策略", "发布订阅模式", "数据结构服务"],
        },
        {
            "name": "Celery",
            "url": "https://github.com/celery/celery",
            "description": "分布式任务队列，支持异步任务调度",
            "category": "tool",
            "tags": ["task-queue", "async", "distributed"],
            "key_insights": ["任务队列模式", "工作流调度", "结果后端"],
        },
        {
            "name": "Nginx",
            "url": "https://github.com/nginx/nginx",
            "description": "高性能 Web 服务器和反向代理",
            "category": "tool",
            "tags": ["web-server", "proxy", "load-balancing"],
            "key_insights": ["事件驱动架构", "反向代理模式", "负载均衡策略"],
        },
        # ---- 架构模式 ----
        {
            "name": "Event Sourcing",
            "url": "https://martinfowler.com/eaaDev/EventSourcing.html",
            "description": "事件溯源架构，以事件序列存储状态变更",
            "category": "architecture",
            "tags": ["event-driven", "cqrs", "ddd"],
            "key_insights": ["事件存储模式", "状态重建", "事件回溯"],
        },
        {
            "name": "CQRS",
            "url": "https://martinfowler.com/bliki/CQRS.html",
            "description": "命令查询职责分离，读写分离架构",
            "category": "architecture",
            "tags": ["architecture", "read-write", "scalability"],
            "key_insights": ["读写分离", "命令模式", "查询优化"],
        },
        {
            "name": "Microservices",
            "url": "https://microservices.io/",
            "description": "微服务架构模式，服务独立部署和扩展",
            "category": "architecture",
            "tags": ["architecture", "distributed", "scalability"],
            "key_insights": ["服务拆分", "服务发现", "API 网关"],
        },
        {
            "name": "Clean Architecture",
            "url": "https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html",
            "description": "整洁架构，依赖反转和用例驱动",
            "category": "architecture",
            "tags": ["architecture", "ddd", "solid"],
            "key_insights": ["依赖反转原则", "用例驱动", "边界隔离"],
        },
        # ---- 算法/数据结构 ----
        {
            "name": "Bloom Filter",
            "url": "https://github.com/bitly/dablooms",
            "description": "布隆过滤器，高效集合成员判断",
            "category": "algorithm",
            "tags": ["probabilistic", "set", "memory"],
            "key_insights": ["概率性数据结构", "假阳性控制", "空间效率"],
        },
        {
            "name": "Skip List",
            "url": "https://en.wikipedia.org/wiki/Skip_list",
            "description": "跳表，有序数据结构，支持 O(log n) 查找",
            "category": "algorithm",
            "tags": ["data-structure", "ordered", "log-n"],
            "key_insights": ["多层索引", "概率平衡", "范围查询优化"],
        },
        {
            "name": "LSM Tree",
            "url": "https://github.com/google/leveldb",
            "description": "日志结构合并树，LSM 存储引擎核心",
            "category": "algorithm",
            "tags": ["storage", "write-optimized", "nosql"],
            "key_insights": ["顺序写入", "层级合并", "写放大控制"],
        },
        # ---- 模板 ----
        {
            "name": "Cookiecutter",
            "url": "https://github.com/cookiecutter/cookiecutter",
            "description": "项目模板生成器，从模板创建新项目",
            "category": "template",
            "tags": ["template", "scaffold", "automation"],
            "key_insights": ["模板化生成", "变量替换", "钩子机制"],
        },
        {
            "name": "uv",
            "url": "https://github.com/astral-sh/uv",
            "description": "极速 Python 包管理器，替代 pip",
            "category": "tool",
            "tags": ["python", "package-manager", "performance"],
            "key_insights": ["依赖解析优化", "并行下载", "缓存策略"],
        },
    ]

    def __init__(self, library: Library | None = None) -> None:
        self._library = library
        self._projects: dict[str, GitHubProject] = {}
        self._cache: dict[str, tuple[float, Any]] = {}
        self.__remaining: int = 60
        self.__reset_time: float = time.time() + 3600
        self._load_builtin()

    def _load_builtin(self) -> None:
        """加载内置精选项目。"""
        for item in self._BUILTIN_PROJECTS:
            project = GitHubProject(
                name=item["name"],
                url=item["url"],
                description=item["description"],
                category=ProjectCategory(item["category"]),
                tags=item.get("tags", []),
                key_insights=item.get("key_insights", []),
            )
            self._projects[item["name"]] = project

            # 同步到资料库
            if self._library:
                content = (
                    f"项目: {project.name}\n"
                    f"描述: {project.description}\n"
                    f"分类: {project.category.value}\n"
                    f"标签: {', '.join(project.tags)}\n"
                    f"关键洞见:\n" + "\n".join(f"  - {i}" for i in project.key_insights)
                )
                self._library.store(
                    title=f"[GitHub] {project.name}",
                    content=content,
                    scope=LibraryScope.GLOBAL,
                    tags=project.tags,
                    author="GitHub Knowledge",
                )

        logger.info("GitHub 知识: 加载 %d 个内置项目", len(self._projects))

    # ---- 查询 ----

    def search(self, query: str, top_k: int = 5) -> list[GitHubProject]:
        """搜索项目。"""
        query_lower = query.lower()
        scored: ClassVar[list[tuple[float, GitHubProject]]] = []

        for project in self._projects.values():
            score = 0.0
            if query_lower in project.name.lower():
                score += 3.0
            if query_lower in project.description.lower():
                score += 2.0
            for tag in project.tags:
                if query_lower in tag.lower():
                    score += 1.0
            for insight in project.key_insights:
                if query_lower in insight.lower():
                    score += 1.5
            if score > 0:
                scored.append((score, project))

        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:top_k]]

    def get_by_category(self, category: ProjectCategory) -> list[GitHubProject]:
        """按分类获取项目。"""
        return [p for p in self._projects.values() if p.category == category]

    def get_by_tag(self, tag: str) -> list[GitHubProject]:
        """按标签获取项目。"""
        return [p for p in self._projects.values() if tag in p.tags]

    # ---- 统计 ----

    def stats(self) -> dict[str, Any]:
        """知识融合统计。"""
        categories: ClassVar[ClassVar[dict[str, int]]] = {}
        languages: ClassVar[ClassVar[dict[str, int]]] = {}
        for p in self._projects.values():
            categories[p.category.value] = categories.get(p.category.value, 0) + 1
            if p.language:
                languages[p.language] = languages.get(p.language, 0) + 1
        return {
            "total_projects": len(self._projects),
            "by_category": categories,
            "by_language": languages,
        }

    # ---- 缓存 / 速率限制 ----

    @property
    def _remaining(self) -> int:
        return self.__remaining

    @_remaining.setter
    def _remaining(self, v: int) -> None:
        self.__remaining = v

    @property
    def _reset_time(self) -> float:
        return self.__reset_time

    @_reset_time.setter
    def _reset_time(self, v: float) -> None:
        self.__reset_time = v

    def get_cached(self, key: str, ttl: int = 300) -> Any | None:
        """获取缓存项，过期返回 None。
        Args:
            key: 缓存键。
            ttl: 存活秒数（默认 300s）。
        Returns:
            缓存值或 None。
        """
        entry = self._cache.get(key)
        if entry is None:
            return None
        stamped, value = entry
        if time.time() - stamped > ttl:
            del self._cache[key]
            return None
        return value

    def invalidate_cache(self, pattern: str) -> int:
        """按 glob 模式清除缓存项。
        Args:
            pattern: glob 匹配模式（如 'search:*'）。
        Returns:
            清除的条目数。
        """
        keys = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
        for k in keys:
            del self._cache[k]
        return len(keys)

    def to_dict(self) -> dict[str, Any]:
        """导出知识融合状态。"""
        return {
            "projects": [
                {
                    "name": p.name,
                    "url": p.url,
                    "description": p.description,
                    "category": p.category.value,
                    "tags": p.tags,
                    "key_insights": p.key_insights,
                }
                for p in self._projects.values()
            ],
            "stats": self.stats(),
        }
