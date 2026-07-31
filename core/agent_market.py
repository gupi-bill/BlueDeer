"""Agent 市场 — 注册表持久化 + 分类浏览 + 安装管理。

能力：
    - 持久化已注册 Agent 列表到 JSON
    - 按类别（内置 / 远程 / 自定义）分组
    - 安装 / 卸载 Agent（复制文件到 modules/）
    - 按名称 / 能力 / 标签搜索
    - 统计每个 Agent 的任务数据（从 audit 日志聚合）
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from core.agent_registry import AgentInfo, AgentRegistry

logger = logging.getLogger("bluedeer.agent_market")

_MARKET_FILE = "logs/agent_market.json"
_MODULES_DIR = "modules"


@dataclass
class MarketAgent:
    info: AgentInfo
    installed_at: float = 0
    install_path: str = ""
    stats: dict[str, Any] = field(default_factory=lambda: {
        "total_tasks": 0, "success": 0, "failed": 0,
        "avg_duration_ms": 0, "last_active": 0,
    })
    featured: bool = False
    category: str = "builtin"


class AgentMarket:
    def __init__(self, registry: AgentRegistry | None = None, market_file: str = _MARKET_FILE) -> None:
        self._registry = registry or AgentRegistry()
        self._market_file = market_file
        self._agents: dict[str, MarketAgent] = {}
        self._load()
        os.makedirs(os.path.dirname(self._market_file) or ".", exist_ok=True)

    def register(self, agent_cls: type, *, source: str = "builtin", source_url: str = "", category: str = "builtin", featured: bool = False) -> None:
        self._registry.register(agent_cls, source=source, source_url=source_url)
        info = self._registry.get_agent(agent_cls.__name__)
        if not info:
            return
        if info.name not in self._agents:
            self._agents[info.name] = MarketAgent(
                info=info, category=category, featured=featured,
            )
        self._save()

    def list_agents(self, category: str = "") -> list[dict[str, Any]]:
        agents = self._agents.values()
        if category:
            agents = [a for a in agents if a.category == category]
        return [self._to_dict(a) for a in agents]

    def search(self, query: str) -> list[dict[str, Any]]:
        results = self._registry.search(query)
        ids = {a.name for a in results}
        return [self._to_dict(self._agents[n]) for n in ids if n in self._agents]

    def get_agent(self, name: str) -> dict[str, Any] | None:
        a = self._agents.get(name)
        return self._to_dict(a) if a else None

    def get_categories(self) -> list[str]:
        return list({a.category for a in self._agents.values()})

    def update_stats(self, name: str, **stats: Any) -> None:
        a = self._agents.get(name)
        if a:
            a.stats.update(stats)
            self._save()

    def install(self, name: str, source_path: str) -> bool:
        """安装 Agent：将源目录复制到 modules/ 下。"""
        if name not in self._agents:
            return False
        src = Path(source_path)
        if not src.is_dir():
            logger.warning("安装源不存在: %s", source_path)
            return False
        dst = Path(_MODULES_DIR) / name.lower()
        if dst.exists():
            logger.warning("模块目录已存在: %s", dst)
            return False
        try:
            shutil.copytree(str(src), str(dst))
            self._agents[name].install_path = str(dst)
            self._agents[name].installed_at = time.time()
            self._agents[name].info.source = "installed"
            self._save()
            logger.info("Agent %s 已安装到 %s", name, dst)
            return True
        except Exception as e:
            logger.exception("安装 Agent %s 失败", name)
            return False

    def uninstall(self, name: str) -> bool:
        a = self._agents.get(name)
        if not a or not a.install_path:
            return False
        try:
            dst = Path(a.install_path)
            if dst.exists():
                shutil.rmtree(str(dst))
            a.install_path = ""
            a.installed_at = 0
            a.info.source = "builtin"
            self._save()
            return True
        except Exception:
            return False

    def refresh_from_registry(self) -> None:
        for info in self._registry.list_agents():
            if info.name not in self._agents:
                self._agents[info.name] = MarketAgent(info=info)
        self._save()

    def recommend(self, user_profile: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        """基于能力匹配推荐 Agent。"""
        if not user_profile or not self._agents:
            return []
        profile_set = set(c.lower() for c in user_profile)
        scored: list[tuple[float, MarketAgent]] = []
        for agent in self._agents.values():
            caps = set(c.lower() for c in agent.info.capabilities)
            if not caps:
                continue
            overlap = len(profile_set & caps)
            jaccard = overlap / len(profile_set | caps) if profile_set | caps else 0
            score = jaccard * 0.7 + (overlap / len(profile_set)) * 0.3 if profile_set else 0
            scored.append((score, agent))
        scored.sort(key=lambda x: -x[0])
        return [self._to_dict(a) for s, a in scored[:top_k]]

    def rate(self, agent_id: str, score: float) -> bool:
        """用户评分（1-5）。"""
        agent = self._agents.get(agent_id)
        if agent is None or not 1 <= score <= 5:
            return False
        ratings = agent.stats.setdefault("ratings", [])
        ratings.append(score)
        agent.stats["avg_rating"] = sum(ratings) / len(ratings)
        self._save()
        return True

    def top_rated(self, k: int = 10) -> list[dict[str, Any]]:
        """按评分排序返回 Top K Agent。"""
        scored = []
        for agent in self._agents.values():
            avg = agent.stats.get("avg_rating", 0)
            r_count = len(agent.stats.get("ratings", []))
            if r_count == 0:
                continue
            scored.append((avg, r_count, agent))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [self._to_dict(a) for _, _, a in scored[:k]]

    def _to_dict(self, a: MarketAgent) -> dict[str, Any]:
        return {
            "name": a.info.name,
            "qualified_name": a.info.qualified_name,
            "role": a.info.role,
            "description": a.info.description,
            "capabilities": a.info.capabilities,
            "version": a.info.version,
            "enabled": a.info.enabled,
            "source": a.info.source,
            "source_url": a.info.source_url,
            "tags": a.info.tags,
            "category": a.category,
            "featured": a.featured,
            "installed": bool(a.install_path),
            "installed_at": a.installed_at,
            "stats": a.stats,
        }

    def _save(self) -> None:
        try:
            data = []
            for a in self._agents.values():
                d = asdict(a)
                d["info"] = asdict(a.info)
                data.append(d)
            with open(self._market_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存 Agent 市场数据失败: %s", e)

    def _load(self) -> None:
        try:
            if not os.path.exists(self._market_file):
                return
            with open(self._market_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data:
                info = AgentInfo(**d.pop("info", {}))
                ma = MarketAgent(info=info, **d)
                self._agents[info.name] = ma
                self._registry._agents[info.name] = info
        except Exception as e:
            logger.warning("加载 Agent 市场数据失败: %s", e)


# 全局单例
_market: AgentMarket | None = None


def get_market() -> AgentMarket:
    global _market
    if _market is None:
        _market = AgentMarket()
    return _market
