"""commit 38：组织经验库。

零基础读者可以这样理解：
- 智能体每完成一次任务后，会复盘出一条"经验"（哪里顺利、哪里卡壳）
- 经验存进这个库，按"任务类型"分类
- 下次同类任务，智能体会自动检索相关经验，注入到 prompt 里参考
- 经验有"权重"：用了之后效果好 +1，效果差 -1，归零自动删除
- 经验库是公司的"组织记忆"，不随个体死亡而消失

存储路径：data/experience_library.json
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
import os
import threading
import time
import uuid

# ----------------------------------------------------------------------
# 存储路径
# ----------------------------------------------------------------------

_EXPERIENCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "experience_library.json",
)


# ----------------------------------------------------------------------
# 任务类型关键词映射（18 种）
# ----------------------------------------------------------------------

TASK_TYPE_KEYWORDS: dict[str, list[str]] = {
    "代码生成-算法实现": [
        "排序",
        "查找",
        "算法",
        "树",
        "图",
        "动态规划",
        "递归",
        "sort",
        "search",
        "algorithm",
    ],
    "代码生成-安全相关": [
        "加密",
        "哈希",
        "签名",
        "证书",
        "密码",
        "登录",
        "cipher",
        "hash",
        "auth",
        "login",
    ],
    "代码生成-业务逻辑": [
        "业务",
        "接口",
        "API",
        "实现",
        "功能",
        "module",
        "function",
        "class",
        "service",
    ],
    "UI-界面设计": [
        "ui",
        "界面",
        "页面",
        "设计",
        "布局",
        "css",
        "html",
        "样式",
        "组件",
    ],
    "UI-交互体验": ["交互", "动画", "动效", "反馈", "hover", "click"],
    "测试-单元测试": ["单元测试", "unit test", "pytest", "unittest", "用例"],
    "测试-模糊测试": ["fuzz", "模糊测试", "随机测试", "边界"],
    "测试-覆盖率": ["覆盖", "coverage", "branch", "行覆盖"],
    "安全-漏洞扫描": ["漏洞", "vulnerability", "扫描", "scan", "cve"],
    "安全-审计": ["审计", "audit", "review", "代码审查"],
    "运维-部署": ["部署", "deploy", "上线", "发布", "release"],
    "运维-存储": ["存储", "kv", "事务", "txn", "bitcask", "lsm", "mvcc"],
    "检索-向量": ["向量", "embedding", "rag", "语义检索"],
    "检索-倒排": ["倒排", "inverted", "索引", "关键词搜索"],
    "统计-数据分析": ["统计", "回归", "分布", "均值", "方差", "异常检测"],
    "网络-接口调试": ["http", "grpc", "dns", "websocket", "接口调试"],
    "监控-告警": ["监控", "告警", "metric", "仪表盘", "dashboard", "alert"],
    "调度-拓扑规划": ["调度", "拓扑", "约束", "规划", "critical path", "csp"],
}


def classify_task_type(task: str) -> str:
    """从任务文本识别任务类型。未匹配返回"其他"。

    匹配规则：统计每个类型的关键词命中数，取最高分。
    """
    if not task:
        return "其他"
    task_lower = task.lower()
    best_type = "其他"
    best_score = 0
    for t, keywords in TASK_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in task_lower)
        if score > best_score:
            best_score = score
            best_type = t
    return best_type


# ----------------------------------------------------------------------
# 经验库单例
# ----------------------------------------------------------------------


class ExperienceLibrary:
    """组织经验库（单例）。

    存储结构：
        {
            "experiences": [
                {
                    "id": "exp-xxxx",
                    "task_type": "代码生成-算法实现",
                    "agent_species": "squirrel",
                    "task_summary": "写一个排序算法",
                    "lesson": "先检查边界条件再写主体",
                    "weight": 1,
                    "adopted_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "created_ts": 1234567890,
                    "last_used_ts": 0,
                },
                ...
            ]
        }
    """

    _instance: ExperienceLibrary | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._experiences: list[dict] = []
        self._loaded = False
        self._load()

    @classmethod
    def get_instance(cls) -> ExperienceLibrary:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------- 持久化 ----------------

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            try:
                if os.path.exists(_EXPERIENCE_PATH):
                    with open(_EXPERIENCE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._experiences = data.get("experiences", []) or []
            except (json.JSONDecodeError, OSError):
                self._experiences = []
            self._loaded = True

    def _save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(_EXPERIENCE_PATH), exist_ok=True)
                with open(_EXPERIENCE_PATH, "w", encoding="utf-8") as f:
                    json.dump(
                        {"experiences": self._experiences},
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except OSError:
                logger.exception("Exception in block")

    # ---------------- 写入 ----------------

    def add_experience(
        self,
        agent_species: str,
        task_summary: str,
        lesson: str,
        task_type: str = "",
        improvement: str = "",
    ) -> str:
        """添加一条经验。返回经验 ID。

        Args:
            agent_species: 物种代号（如 "squirrel"）
            task_summary: 任务简述（如 "写排序算法"）
            lesson: 学到的经验（如 "先检查边界条件"）
            task_type: 任务类型；为空时自动分类
            improvement: 改进建议（可选）
        """
        if not lesson or not lesson.strip():
            return ""
        if not task_type:
            task_type = classify_task_type(task_summary)
        exp_id = "exp-" + uuid.uuid4().hex[:8]
        exp = {
            "id": exp_id,
            "task_type": task_type,
            "agent_species": agent_species,
            "task_summary": (task_summary or "")[:200],
            "lesson": lesson.strip()[:500],
            "improvement": (improvement or "").strip()[:500],
            "weight": 1,  # 初始权重 1
            "adopted_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "created_ts": time.time(),
            "last_used_ts": 0,
        }
        with self._lock:
            self._experiences.append(exp)
            # 上限 500 条，超出按权重和时间淘汰
            if len(self._experiences) > 500:
                self._experiences.sort(
                    key=lambda x: (x.get("weight", 0), x.get("last_used_ts", 0)),
                    reverse=True,
                )
                self._experiences = self._experiences[:500]
            self._save()
        return exp_id

    def adopt_experience(self, exp_id: str, agent_species: str, better: bool) -> dict:
        """记录某智能体采用了一条经验，并更新权重。

        Args:
            exp_id: 经验 ID
            agent_species: 采用方物种
            better: True=效果好（权重 +1），False=效果差（权重 -1）

        Returns:
            更新后的经验 dict（如果经验被删除则返回 {"deleted": True}）
        """
        with self._lock:
            for i, exp in enumerate(self._experiences):
                if exp.get("id") == exp_id:
                    exp["adopted_count"] = exp.get("adopted_count", 0) + 1
                    exp["last_used_ts"] = time.time()
                    if better:
                        exp["weight"] = exp.get("weight", 0) + 1
                        exp["success_count"] = exp.get("success_count", 0) + 1
                    else:
                        exp["weight"] = exp.get("weight", 0) - 1
                        exp["failure_count"] = exp.get("failure_count", 0) + 1
                    # 权重归零则删除
                    if exp["weight"] <= 0:
                        self._experiences.pop(i)
                        self._save()
                        return {"deleted": True, "id": exp_id}
                    self._save()
                    return exp
        return {"not_found": True, "id": exp_id}

    # ---------------- 检索 ----------------

    def search_experiences(
        self, task_type: str = "", agent_species: str = "", limit: int = 5
    ) -> list[dict]:
        """按任务类型和物种检索经验。

        排序规则：权重降序 + 最近使用时间降序。
        """
        with self._lock:
            results = []
            for exp in self._experiences:
                if task_type and exp.get("task_type") != task_type:
                    continue
                if agent_species and exp.get("agent_species") != agent_species:
                    continue
                results.append(dict(exp))
            results.sort(
                key=lambda x: (x.get("weight", 0), x.get("last_used_ts", 0)),
                reverse=True,
            )
            return results[:limit]

    def search_by_task(
        self, task: str, agent_species: str = "", limit: int = 5
    ) -> list[dict]:
        """按任务文本检索相关经验。

        先按任务类型筛选，再按物种筛选（物种为空则取全部），
        最后按权重排序。
        """
        task_type = classify_task_type(task)
        # 先精确匹配任务类型
        results = self.search_experiences(
            task_type=task_type, agent_species=agent_species, limit=limit
        )
        # 如果该物种没经验，取同任务类型其他物种的经验
        if not results and agent_species:
            results = self.search_experiences(
                task_type=task_type, agent_species="", limit=limit
            )
        return results

    # ---------------- 查询 ----------------

    def list_all(self, task_type: str = "", limit: int = 100) -> list[dict]:
        """列出全部经验（按权重降序）。"""
        with self._lock:
            results = []
            for exp in self._experiences:
                if task_type and exp.get("task_type") != task_type:
                    continue
                results.append(dict(exp))
            results.sort(
                key=lambda x: (x.get("weight", 0), x.get("created_ts", 0)), reverse=True
            )
            return results[:limit]

    def stats(self) -> dict:
        """统计信息：总数、按物种分布、按任务类型分布。"""
        with self._lock:
            by_species: dict[str, int] = {}
            by_type: dict[str, int] = {}
            total_weight = 0
            for exp in self._experiences:
                sp = exp.get("agent_species", "unknown")
                by_species[sp] = by_species.get(sp, 0) + 1
                t = exp.get("task_type", "其他")
                by_type[t] = by_type.get(t, 0) + 1
                total_weight += exp.get("weight", 0)
            return {
                "total": len(self._experiences),
                "by_species": by_species,
                "by_type": by_type,
                "total_weight": total_weight,
            }


# ----------------------------------------------------------------------
# 模块级便捷 API
# ----------------------------------------------------------------------


def get_experience_library() -> ExperienceLibrary:
    return ExperienceLibrary.get_instance()


def add_experience(
    agent_species: str, task_summary: str, lesson: str, task_type: str = ""
) -> str:
    return get_experience_library().add_experience(
        agent_species, task_summary, lesson, task_type=task_type
    )


def search_experiences_by_task(
    task: str, agent_species: str = "", limit: int = 5
) -> list[dict]:
    return get_experience_library().search_by_task(
        task, agent_species=agent_species, limit=limit
    )


def format_experiences_for_prompt(experiences: list[dict]) -> str:
    """把经验列表格式化成可注入 prompt 的字符串。"""
    if not experiences:
        return ""
    lines = []
    for i, exp in enumerate(experiences, 1):
        lines.append(
            f"{i}. [{exp.get('task_type', '')}] {exp.get('lesson', '')}"
            f"（来自 {exp.get('agent_species', '')}，权重 {exp.get('weight', 0)}）"
        )
    return "\n".join(lines)
