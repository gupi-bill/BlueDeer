"""commit 35：虚拟工作产物系统。

零基础读者可以这样理解：
- 智能体工作不再是抽象的"任务数+1"，而是产生可见的虚拟产物
- 松鼠的代码片段、蝶的UI设计稿、狐的测试报告...每个物种有独特产物
- 产物会逐渐堆积在工位附近，让工作有"痕迹"
- 资料库新增"成果展示墙"，展示每个智能体最得意的作品
- 监工可点赞，点赞提升该智能体的 joy

文件存储路径：data/memory/{agent_id}_artifacts.json
"""
from __future__ import annotations

import datetime
import json
import os
import random
import threading
import time
from typing import Any

# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------

ARTIFACT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "memory",
)

MAX_ARTIFACTS_PER_AGENT = 30      # 工位附近最多保留 30 件产物
MAX_WALL_ITEMS = 50               # 成果展示墙最多 50 件
PRODUCE_INTERVAL = 1800           # 每 30 分钟尝试生成一件新产物


# ----------------------------------------------------------------------
# 物种 → 产物类型
# ----------------------------------------------------------------------

SPECIES_ARTIFACT_TYPES: dict[str, dict] = {
    "squirrel": {
        "kind": "code_snippet",
        "label": "代码片段",
        "color": "rgba(140,210,150,0.9)",
        "icon": "📜",
        # 降级模板（LLM 不可用时）
        "templates": [
            "def process_payment(order):\n    if not order.validate():\n        raise InvalidOrder\n    return charge(order.amount)",
            "class PaymentService:\n    def __init__(self, gateway):\n        self.gateway = gateway\n\n    def refund(self, tx_id):\n        return self.gateway.refund(tx_id)",
            "async def sync_ledger():\n    async with db.transaction():\n        await reconcile_entries()",
        ],
        "prompts": ["生成一段支付模块的 Python 函数代码，30-60 字，要逼真"],
    },
    "butterfly": {
        "kind": "ui_design",
        "label": "UI 设计稿",
        "color": "rgba(255,150,200,0.9)",
        "icon": "🎨",
        "templates": [
            "暮色蓝配色方案：主色 #2C3E50，强调色 #E74C3C，背景 #ECF0F1",
            "支付按钮设计：圆角 8px，渐变色 #3498DB→#2980B9，悬停时上浮 2px",
            "移动端导航：底部 tab bar，5 个图标，中央凸起+按钮",
        ],
        "prompts": ["用一句话描述一个 UI 设计方案，包含色值和细节"],
    },
    "fox": {
        "kind": "test_report",
        "label": "测试报告",
        "color": "rgba(255,180,100,0.9)",
        "icon": "🐛",
        "templates": [
            "今日测试：通过 47 / 失败 2。失败用例：PaymentRefundTest.test_timeout、AuthTest.test_expired_token",
            "测试覆盖率达到 87%。最薄弱模块：refund_service（62%），建议补充边界用例",
            "性能测试：1000 QPS 下平均响应 120ms，P99 280ms，符合 SLA",
        ],
        "prompts": ["生成一份简短测试报告，包含通过/失败统计和一个具体 bug"],
    },
    "beaver": {
        "kind": "deploy_status",
        "label": "部署面板",
        "color": "rgba(140,180,220,0.9)",
        "icon": "🛠",
        "templates": [
            "部署状态：v2.3.1 已上线 5/5 节点。服务正常。耗时 3 分 42 秒",
            "水坝机房例行维护：替换 2 块腐朽木板，加固西北角支点",
            "回滚操作：v2.3.2 → v2.3.1，原因：内存泄漏。已修复",
        ],
        "prompts": ["生成一条部署状态简报，包含版本号和状态"],
    },
    "raven": {
        "kind": "memory_card",
        "label": "记忆索引卡",
        "color": "rgba(200,180,255,0.9)",
        "icon": "🗂",
        "templates": [
            "记忆卡片 #2025-001：关键词【大洪水】，2025-07-15，3 人参与，影响持续 2 天",
            "记忆卡片 #2025-002：关键词【鹿·一代退休】，2025-08-20，全员到场送别",
            "记忆卡片 #2025-003：关键词【首次急救成功】，2025-09-03，渡鸦+海狸+鹿协作",
        ],
        "prompts": ["生成一张记忆索引卡片，包含编号、关键词、日期、参与人"],
    },
    "hare": {
        "kind": "resource_report",
        "label": "资源报表",
        "color": "rgba(255,220,150,0.9)",
        "icon": "📊",
        "templates": [
            "资源日报：Token 消耗 2.3M / 预算 5M，剩余可用 3 天 12 小时",
            "坚果库存：3,247 颗，预计 18 天后耗尽。建议补货 5,000 颗",
            "本月开销：LLM 调用 80%，存储 12%，其他 8%。比上月节省 8%",
        ],
        "prompts": ["生成一份简短资源报表，包含数字和具体含义"],
    },
    "badger": {
        "kind": "api_adapter",
        "label": "接口适配记录",
        "color": "rgba(180,220,180,0.9)",
        "icon": "🔌",
        "templates": [
            "适配记录：外部支付网关 v2 → v3 迁移。新增字段：merchant_id，废弃：legacy_token",
            "适配记录：发票服务 API 重构，统一字段命名 snake_case",
            "适配记录：报表导出接口增加分页参数 page_size（默认 100）",
        ],
        "prompts": ["生成一条接口适配记录，包含版本和具体变化"],
    },
    "lark": {
        "kind": "status_flag",
        "label": "状态快照",
        "color": "rgba(255,240,150,0.9)",
        "icon": "🚩",
        "templates": [
            "状态快照 06:00：全员健康，0 告警。最先醒来的是雀·晨曦",
            "状态快照 12:00：3 人在午休，8 人在工作。系统平均负载 42%",
            "状态快照 18:00：今日完成 23 个任务，0 逾期。森林公司运转良好",
        ],
        "prompts": ["生成一条状态快照，包含时间和全员状态描述"],
    },
    "deer": {
        "kind": "dispatch_panel",
        "label": "调度面板",
        "color": "rgba(255,200,150,0.9)",
        "icon": "📋",
        "templates": [
            "调度记录：分配 3 个任务给松鼠组，2 个给狐组。平均完成时间 2.3 小时",
            "调度记录：紧急插队任务 #1024 优先级 P0，已分配给猬+狐组合",
            "调度记录：今日任务流转 27 次，瓶颈在工作台 B（等待 12 分钟）",
        ],
        "prompts": ["生成一条调度面板记录，包含任务分配和效率数据"],
    },
    "hedgehog": {
        "kind": "security_log",
        "label": "安全日志",
        "color": "rgba(255,140,140,0.9)",
        "icon": "🛡",
        "templates": [
            "安全日志：今日拦截异常访问 3 次。IP 198.51.100.42 已加入黑名单",
            "安全日志：漏洞扫描完成，发现 1 个低危问题（已通知狐）",
            "安全日志：堡垒墙例行检查通过，无破损",
        ],
        "prompts": ["生成一条安全日志，包含具体威胁或扫描结果"],
    },
    "kite": {
        "kind": "gantt_projection",
        "label": "甘特图投影",
        "color": "rgba(180,200,255,0.9)",
        "icon": "📅",
        "templates": [
            "甘特投影：本周 12 个任务，关键路径 5 天。瓶颈：测试阶段（狐组）",
            "甘特投影：下季度项目时间线已规划，里程碑 3 个，预计 90 天",
            "甘特投影：当前进度健康，预计按时交付率 92%",
        ],
        "prompts": ["生成一条甘特图投影记录，包含任务数和进度"],
    },
}


# ----------------------------------------------------------------------
# 单件产物
# ----------------------------------------------------------------------

class Artifact:
    __slots__ = (
        "agent_id",
        "agent_name",
        "archived",
        "color",
        "content",
        "display_x",
        "display_y",
        "icon",
        "id",
        "is_featured",
        "kind",
        "label",
        "liked_by_supervisor",
        "likes",
        "species",
        "time",
        "ts",
    )

    def __init__(self, aid: int, agent_id: str, agent_name: str, species: str,
                 kind: str, label: str, color: str, icon: str,
                 content: str, display_x: float = 0, display_y: float = 0):
        self.id = aid
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.species = species
        self.kind = kind
        self.label = label
        self.color = color
        self.icon = icon
        self.content = content
        self.ts = time.time()
        self.time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.likes = 0
        self.liked_by_supervisor = False
        self.is_featured = False    # 是否入选成果展示墙
        self.display_x = display_x
        self.display_y = display_y
        self.archived = False       # 是否已归档到资料库

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "species": self.species,
            "kind": self.kind,
            "label": self.label,
            "color": self.color,
            "icon": self.icon,
            "content": self.content,
            "ts": self.ts,
            "time": self.time,
            "likes": self.likes,
            "liked_by_supervisor": self.liked_by_supervisor,
            "is_featured": self.is_featured,
            "display_x": round(self.display_x, 2),
            "display_y": round(self.display_y, 2),
            "archived": self.archived,
        }


# ----------------------------------------------------------------------
# 单个智能体的产物集
# ----------------------------------------------------------------------

class AgentArtifacts:
    __slots__ = (
        "_dirty",
        "_lock",
        "_next_id",
        "active",
        "agent_id",
        "agent_name",
        "archived",
        "last_produce_ts",
        "species",
    )

    def __init__(self, agent_id: str, agent_name: str = "", species: str = "") -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.species = species
        self.active: list[Artifact] = []      # 工位附近可见的
        self.archived: list[Artifact] = []    # 已归档到资料库
        self._lock = threading.RLock()
        self._dirty = False
        self.last_produce_ts: float = 0.0
        self._next_id: int = 1

    def _path(self) -> str:
        return os.path.join(ARTIFACT_DIR, f"{self.agent_id}_artifacts.json")

    def load(self) -> None:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        with self._lock:
            try:
                with open(self._path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.agent_name = data.get("agent_name", self.agent_name)
                self.species = data.get("species", self.species)
                self._next_id = int(data.get("next_id", 1))
                self.last_produce_ts = float(data.get("last_produce_ts", 0.0))
                self.active = [self._dict_to_art(d) for d in data.get("active", [])]
                self.archived = [self._dict_to_art(d) for d in data.get("archived", [])]
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            self._dirty = False

    def _dict_to_art(self, d: dict) -> Artifact:
        a = Artifact(
            aid=d.get("id", 0),
            agent_id=d.get("agent_id", self.agent_id),
            agent_name=d.get("agent_name", self.agent_name),
            species=d.get("species", self.species),
            kind=d.get("kind", ""),
            label=d.get("label", ""),
            color=d.get("color", ""),
            icon=d.get("icon", ""),
            content=d.get("content", ""),
            display_x=d.get("display_x", 0),
            display_y=d.get("display_y", 0),
        )
        a.ts = d.get("ts", 0)
        a.time = d.get("time", "")
        a.likes = d.get("likes", 0)
        a.liked_by_supervisor = d.get("liked_by_supervisor", False)
        a.is_featured = d.get("is_featured", False)
        a.archived = d.get("archived", False)
        return a

    def save(self) -> None:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        with self._lock:
            if not self._dirty:
                return
            try:
                payload = {
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "species": self.species,
                    "next_id": self._next_id,
                    "last_produce_ts": self.last_produce_ts,
                    "active": [a.to_dict() for a in self.active],
                    "archived": [a.to_dict() for a in self.archived],
                }
                tmp = self._path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._path())
                self._dirty = False
            except Exception:
                pass

    def produce(self, content: str | None = None,
                 display_x: float = 0, display_y: float = 0) -> Artifact | None:
        """生成一件新产物。"""
        spec = SPECIES_ARTIFACT_TYPES.get(self.species)
        if spec is None:
            return None
        with self._lock:
            # 上限检查：超出则归档最旧的
            if len(self.active) >= MAX_ARTIFACTS_PER_AGENT:
                oldest = min(self.active, key=lambda a: a.ts)
                oldest.archived = True
                self.active.remove(oldest)
                self.archived.append(oldest)
                # 归档上限 100
                if len(self.archived) > 100:
                    del self.archived[: len(self.archived) - 100]
            if content is None:
                content = random.choice(spec["templates"])
            art = Artifact(
                aid=self._next_id,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                species=self.species,
                kind=spec["kind"],
                label=spec["label"],
                color=spec["color"],
                icon=spec["icon"],
                content=content,
                display_x=display_x,
                display_y=display_y,
            )
            self._next_id += 1
            self.active.append(art)
            self.last_produce_ts = time.time()
            self._dirty = True
            return art

    def like(self, art_id: int, by_supervisor: bool = True) -> bool:
        """点赞一件产物。"""
        with self._lock:
            for a in self.active + self.archived:
                if a.id == art_id:
                    a.likes += 1
                    if by_supervisor:
                        a.liked_by_supervisor = True
                    # 5 赞以上自动入选成果展示墙
                    if a.likes >= 3 and not a.is_featured:
                        a.is_featured = True
                    self._dirty = True
                    return True
            return False

    def get_featured(self) -> list[Artifact]:
        with self._lock:
            return [a for a in self.active + self.archived if a.is_featured]

    def to_dict(self, include_archived: bool = False) -> dict:
        with self._lock:
            data = {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "species": self.species,
                "active_count": len(self.active),
                "archived_count": len(self.archived),
                "active": [a.to_dict() for a in self.active[-10:]],   # 最近 10 件
                "featured": [a.to_dict() for a in self.get_featured()],
            }
            if include_archived:
                data["archived"] = [a.to_dict() for a in self.archived[-20:]]
            return data


# ----------------------------------------------------------------------
# 全局管理器
# ----------------------------------------------------------------------

class WorkArtifactsManager:
    _instance: WorkArtifactsManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._store: dict[str, AgentArtifacts] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> WorkArtifactsManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_or_create(self, agent_id: str, agent_name: str = "",
                       species: str = "") -> AgentArtifacts:
        with self._lock:
            if agent_id not in self._store:
                arts = AgentArtifacts(agent_id, agent_name, species)
                arts.load()
                self._store[agent_id] = arts
            else:
                if agent_name and self._store[agent_id].agent_name != agent_name:
                    self._store[agent_id].agent_name = agent_name
                    self._store[agent_id]._dirty = True
                if species and self._store[agent_id].species != species:
                    self._store[agent_id].species = species
                    self._store[agent_id]._dirty = True
            return self._store[agent_id]

    def save_all(self) -> int:
        count = 0
        with self._lock:
            for a in self._store.values():
                a.save()
                count += 1
        return count

    # ---------------- 生产触发 ----------------

    def maybe_produce(self, agent: Any, router: Any = None,
                       force: bool = False) -> Artifact | None:
        """检查并触发产物生成。force=True 时绕过时间和状态检查。"""
        if agent is None or not getattr(agent, "_alive", False):
            return None
        species = getattr(agent, "species", "")
        if species not in SPECIES_ARTIFACT_TYPES:
            return None
        if not force:
            # 必须在工作状态（兼容 ActionState 枚举和字符串）
            ca = getattr(agent, "current_action", None)
            ca_val = ca.value if hasattr(ca, "value") else ca
            cb = getattr(agent, "current_behavior", None)
            if str(ca_val).lower() != "work" and \
               str(cb).lower() not in ("work", "develop", "test", "design"):
                return None
        agent_id = agent.get_agent_id()
        arts = self.get_or_create(agent_id,
                                    agent_name=getattr(agent, "_name_obj", ""),
                                    species=species)
        if not force:
            now = time.time()
            if now - arts.last_produce_ts < PRODUCE_INTERVAL:
                return None

        # 尝试用 LLM 生成内容
        spec = SPECIES_ARTIFACT_TYPES[species]
        content = None
        if router is not None:
            prompt = random.choice(spec["prompts"]) + "，只输出内容本身，30-100 字"
            content = _generate_via_llm(router, prompt)
        # display position：在工位附近随机
        x = getattr(agent, "x", 0) + random.uniform(-1.5, 1.5)
        y = getattr(agent, "y", 0) + random.uniform(-1.5, 1.5)
        art = arts.produce(content=content, display_x=x, display_y=y)
        if art is None:
            return None

        # 联动 2：监工点赞过的产物 → 写入日记的喜悦
        # 这里只生成产物，点赞逻辑在 like() 中
        return art

    def like_artifact(self, agent_id: str, art_id: int,
                       by_supervisor: bool = True) -> tuple[bool, str, Any]:
        """点赞。返回 (成功, 智能体名, agent实例)。"""
        arts = self._store.get(agent_id)
        if arts is None:
            return False, "", None
        ok = arts.like(art_id, by_supervisor=by_supervisor)
        if not ok:
            return False, arts.agent_name, None
        arts.save()
        return True, arts.agent_name, None

    def get_wall_items(self) -> list[dict]:
        """成果展示墙：所有入选作品。"""
        items: list[dict] = []
        with self._lock:
            for arts in self._store.values():
                for a in arts.get_featured():
                    items.append(a.to_dict())
        # 按点赞数 + 时间排序
        items.sort(key=lambda x: (x.get("likes", 0), x.get("ts", 0)), reverse=True)
        return items[:MAX_WALL_ITEMS]

    def get_all_summary(self) -> list[dict]:
        with self._lock:
            return [a.to_dict(include_archived=False) for a in self._store.values()]

    def get_agent_artifacts(self, agent_id: str, include_archived: bool = False) -> dict | None:
        a = self._store.get(agent_id)
        if a is None:
            return None
        return a.to_dict(include_archived=include_archived)

    def tick(self, dt: float = 1.0, population: list = None,
              router: Any = None) -> list[dict]:
        """每秒调用：尝试生成产物。返回生成事件列表。"""
        events: list[dict] = []
        if population:
            for lf in population:
                try:
                    art = self.maybe_produce(lf, router=router)
                    if art:
                        events.append({
                            "type": "artifact_produced",
                            "agent_name": art.agent_name,
                            "species": art.species,
                            "kind": art.kind,
                            "label": art.label,
                            "preview": art.content[:60],
                            "ts": art.ts,
                        })
                except Exception:
                    pass
        # 定期落盘
        if int(time.time()) % 600 == 0:
            self.save_all()
        return events


# ----------------------------------------------------------------------
# 辅助
# ----------------------------------------------------------------------

def _generate_via_llm(router: Any, prompt: str, timeout: float = 4.0) -> str | None:
    import asyncio
    if router is None:
        return None
    try:
        loop = asyncio.new_event_loop()
        try:
            if hasattr(router, "complete_with_failover"):
                coro = router.complete_with_failover("voice", prompt, agent_id="artifact")
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            elif hasattr(router, "complete"):
                coro = router.complete(prompt)
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            else:
                return None
            text = getattr(resp, "content", None) or str(resp)
            text = text.strip().strip('"\'“”‘’').replace("\n", " ").strip()
            if 10 <= len(text) <= 200:
                return text
            return None
        finally:
            loop.close()
    except Exception:
        return None


# ----------------------------------------------------------------------
# 模块级便捷函数
# ----------------------------------------------------------------------

def get_artifacts_manager() -> WorkArtifactsManager:
    return WorkArtifactsManager.get_instance()


def tick_artifacts(dt: float = 1.0, population: list = None,
                    router: Any = None) -> list[dict]:
    return get_artifacts_manager().tick(dt, population=population, router=router)


def snapshot_artifacts() -> dict:
    mgr = get_artifacts_manager()
    agents = mgr.get_all_summary()
    return {
        "total_agents": len(agents),
        "total_active": sum(a.get("active_count", 0) for a in agents),
        "total_archived": sum(a.get("archived_count", 0) for a in agents),
        "total_featured": sum(len(a.get("featured", [])) for a in agents),
        "wall": mgr.get_wall_items()[:20],   # 前 20 件
        "agents": agents,
    }


def get_agent_artifacts(agent_id: str, include_archived: bool = False) -> dict | None:
    return get_artifacts_manager().get_agent_artifacts(agent_id, include_archived=include_archived)


def like_artifact(agent_id: str, art_id: int) -> tuple[bool, str]:
    ok, name, _ = get_artifacts_manager().like_artifact(agent_id, art_id, by_supervisor=True)
    return ok, name


def force_produce(agent: Any, router: Any = None):
    """强制立即生成一件产物（测试用，绕过状态和时间检查）。"""
    if agent is None:
        return None
    return get_artifacts_manager().maybe_produce(agent, router=router, force=True)
