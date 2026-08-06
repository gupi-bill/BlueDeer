"""智能体主动消息系统。

零基础读者可以这样理解：
- 以前员工只能"被监工问话才回答"，现在员工会主动找监工说话。
- 三类触发：状态类（工作完成/资源预警/健康危机/情绪波动）、
  事件类（新员工入职/员工死亡/关系里程碑/危机警报）、
  社交类（早安问候/分享发现/想念监工/退休愿望）。
- 每类消息都有冷却时间，避免消息轰炸。
- LLM 可用时调 LLM 生成文本，不可用时降级到预置语料库。
- 消息分优先级：low / medium / high，前端按优先级显示气泡 + 浏览器通知。
"""

from __future__ import annotations

import asyncio
import datetime
import random
import time
from typing import Any

# ====================================================================
# 消息分类与优先级
# ====================================================================

# 每个类别的优先级 + 冷却时间（秒）
#   low:    状态/社交类，2~4 小时冷却
#   medium: 一般事件类，无冷却但受全局速率限制
#   high:   危机/死亡/警报，立即发送并触发浏览器通知
MESSAGE_CATEGORIES: dict[str, dict] = {
    # 状态类（低优先级，2 小时冷却）
    "work_done": {"priority": "low", "cooldown": 7200, "label": "工作完成"},
    "resource_warning": {"priority": "low", "cooldown": 7200, "label": "资源预警"},
    "health_crisis": {"priority": "medium", "cooldown": 1800, "label": "健康危机"},
    "emotion_distress": {"priority": "medium", "cooldown": 3600, "label": "情绪波动"},
    # 事件类（中高优先级，无冷却）
    "new_recruit": {"priority": "medium", "cooldown": 0, "label": "新员工入职"},
    "death_notice": {"priority": "high", "cooldown": 0, "label": "员工离世"},
    "relationship_milestone": {
        "priority": "medium",
        "cooldown": 0,
        "label": "关系里程碑",
    },
    "crisis_alert": {"priority": "high", "cooldown": 0, "label": "危机警报"},
    # 社交类（低优先级，4 小时冷却）
    "morning_greeting": {"priority": "low", "cooldown": 14400, "label": "早安问候"},
    "share_discovery": {"priority": "low", "cooldown": 14400, "label": "分享发现"},
    "missing_supervisor": {"priority": "low", "cooldown": 14400, "label": "想念监工"},
    "retirement_wish": {"priority": "medium", "cooldown": 0, "label": "退休愿望"},
    # commit 34：疾病急救相关
    "illness_onset": {"priority": "medium", "cooldown": 1800, "label": "生病通知"},
    "rescue_please": {"priority": "high", "cooldown": 0, "label": "请求急救"},
    "epidemic_alert": {"priority": "high", "cooldown": 0, "label": "疫情警报"},
    "memory_reunion": {"priority": "medium", "cooldown": 0, "label": "重逢问候"},
}

# 全局速率限制：每小时最多推送 N 条（超出则汇总）
HOURLY_LIMIT: int = 10


# ====================================================================
# 语料库（LLM 不可用时降级使用）
# 每个类别 → 每个物种 → 多条候选文本（{name} 占位符会被替换）
# ====================================================================

MESSAGE_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "work_done": {
        "deer": ["鹿·{name}：调度了 {detail}，一切顺利。"],
        "squirrel": ["鼠·{name}：刚写完一段代码，编译过了。"],
        "butterfly": ["蝶·{name}：花房的配色今天调好了。"],
        "fox": ["狐·{name}：又抓到 {detail} 个 bug。"],
        "hedgehog": ["猬·{name}：巡视完毕，无异常。"],
        "beaver": ["狸·{name}：水坝加固完成。"],
        "raven": ["鸦·{name}：今日故事已记录在案。"],
        "hare": ["兔·{name}：今日账目结算完毕。"],
        "badger": ["獾·{name}：地道新支线挖通。"],
        "lark": ["雀·{name}：监控系统全绿。"],
        "kite": ["鸢·{name}：高空巡视完毕。"],
        "_generic": ["{name}：工作完成。"],
    },
    "resource_warning": {
        "hare": ["兔·{name}：Token 还够 {detail} 天，要注意。"],
        "squirrel": ["鼠·{name}：坚果快不够了，能补点吗？"],
        "beaver": ["狸·{name}：水坝材料不太够了。"],
        "_generic": ["{name}：资源有点紧张，请留意。"],
    },
    "health_crisis": {
        "_generic": [
            "{name}：能量只剩 {detail}，有点撑不住了……",
            "{name}：健康不太好，能照看一下吗？",
        ],
    },
    "emotion_distress": {
        "_generic": [
            "{name}：今天有点焦虑，能和你说说吗？",
            "{name}：心里不太舒服，只想找你聊聊。",
            "{name}：最近压力有些大……",
        ],
    },
    "new_recruit": {
        "deer": ["鹿·{name}：新同事 {detail} 已到岗，安排好了。"],
        "kite": ["鸢·{name}：从空中看到新面孔 {detail} 报到了。"],
        "_generic": ["{name}：欢迎新同事 {detail}！"],
    },
    "death_notice": {
        "raven": ["鸦·{name}：{detail} 走了。我会记得它的故事。"],
        "deer": ["鹿·{name}：{detail} 离开了我们。它工作到最后一刻。"],
        "_generic": ["{name}：{detail} 已经不在了。请节哀。"],
    },
    "relationship_milestone": {
        "_generic": [
            "{name}：我和 {detail} 成为挚友了！",
            "{name}：{detail} 和我搭档了，工作顺手多了。",
        ],
    },
    "crisis_alert": {
        "hedgehog": ["猬·{name}：【警报】发现安全威胁：{detail}！请立即处理。"],
        "fox": ["狐·{name}：【警报】代码出现严重 bug：{detail}！"],
        "_generic": ["{name}：【警报】{detail}"],
    },
    "morning_greeting": {
        "lark": ["雀·{name}：早安，监工！今天也一起加油。"],
        "deer": ["鹿·{name}：早上好，今天也请多关照。"],
        "butterfly": ["蝶·{name}：早～花房刚开好，色彩不错。"],
        "_generic": ["{name}：早安。"],
    },
    "share_discovery": {
        "squirrel": ["鼠·{name}：发现一颗超大的代码坚果！快看快看！"],
        "butterfly": ["蝶·{name}：调出一种新配色，叫'暮色蓝'！"],
        "fox": ["狐·{name}：刚才发现松鼠代码里一个特别搞笑的 bug。"],
        "badger": ["獾·{name}：挖地道时挖到一块亮晶晶的矿石。"],
        "_generic": ["{name}：发现了一件有意思的事。"],
    },
    "missing_supervisor": {
        "_generic": [
            "{name}：好久没看到你了，一切都好吗？",
            "{name}：你不在的时候，工作有点孤单。",
            "{name}：想念你巡视的样子。",
        ],
    },
    "retirement_wish": {
        "_generic": [
            "{name}：到了该想想退休的时候了。{detail}",
            "{name}：我的退休愿望是——{detail}",
        ],
    },
}


# ====================================================================
# LLM Prompt 模板
# ====================================================================

LLM_PROMPT_TEMPLATE: str = """你是 BlueDeer 森林公司的智能体 {name}（物种：{species}）。
当前你的状态：能量 {energy:.0f}/100，健康 {health:.0f}/100，主导情感 {top_emotion}。
当前事件类别：{category_label}。
事件上下文：{context}

请用第一人称、20-50 字、符合物种性格的口吻，向监工说一句话。
只输出这句话本身，不要带引号、不要带"——{name}"之类的署名。
"""


# ====================================================================
# 工具函数
# ====================================================================


def get_category_config(category: str) -> dict:
    """获取消息类别的配置（优先级 + 冷却）。"""
    return MESSAGE_CATEGORIES.get(
        category,
        {
            "priority": "low",
            "cooldown": 3600,
            "label": category,
        },
    )


def pick_template(category: str, species: str, name: str, detail: str = "") -> str:
    """从语料库随机选一条模板并填充占位符。

    Args:
        category: 消息类别
        species: 物种名
        name: 智能体名字
        detail: 上下文细节（如任务数、新员工名等）

    Returns:
        填充后的文本
    """
    cat_lib = MESSAGE_TEMPLATES.get(category, {})
    # 优先用物种专属，没有则用 _generic
    pool = cat_lib.get(species) or cat_lib.get("_generic") or ["{name}：{detail}"]
    text = random.choice(pool)
    # 安全替换（避免 KeyError）
    try:
        return text.format(name=name, detail=detail)
    except (KeyError, IndexError):
        return text.replace("{name}", name).replace("{detail}", detail)


def build_llm_prompt(
    name: str,
    species: str,
    energy: float,
    health: float,
    top_emotion: str,
    category: str,
    context: str,
) -> str:
    """构建 LLM prompt。"""
    cfg = get_category_config(category)
    return LLM_PROMPT_TEMPLATE.format(
        name=name,
        species=species,
        energy=energy,
        health=health,
        top_emotion=top_emotion,
        category_label=cfg.get("label", category),
        context=context or "（无额外上下文）",
    )


def generate_via_llm(router: Any, prompt: str, timeout: float = 3.0) -> str | None:
    """同步调用 LLM 生成消息文本。

    Args:
        router: models.router.Router 实例（或任何带 complete_with_failover 的对象）
        prompt: 完整 prompt
        timeout: 超时秒数

    Returns:
        生成的文本，失败返回 None
    """
    if router is None:
        return None
    try:
        # Router 的标准接口是 async complete_with_failover(task_type, prompt, ...)
        # 在生命体线程里同步调用，需要新开 event loop
        loop = asyncio.new_event_loop()
        try:
            # 优先用 complete_with_failover（Router 接口）
            if hasattr(router, "complete_with_failover"):
                task_type = "voice"  # 短文本生成走 voice 任务类型
                coro = router.complete_with_failover(
                    task_type, prompt, agent_id="active_msg"
                )
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            elif hasattr(router, "complete"):
                # 直接 client 接口
                coro = router.complete(prompt)
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            else:
                return None
            # ModelResponse 有 content 字段
            text = getattr(resp, "content", None) or str(resp)
            text = text.strip()
            # 简单清洗：去掉引号、去掉换行
            text = text.strip("\"'“”‘’").replace("\n", " ").strip()
            if 5 <= len(text) <= 200:
                return text
            return None
        finally:
            loop.close()
    except Exception:
        return None


# ====================================================================
# 主动消息触发器
# ====================================================================


def trigger_active_message(
    agent: Any,
    category: str,
    detail: str = "",
    context: str = "",
    router: Any = None,
) -> str | None:
    """触发一条主动消息。

    检查冷却 → 选模板或调 LLM → 推送到 environment 的队列。

    Args:
        agent: DigitalLifeForm 实例（需有 _name_obj / species / emotional_state 等字段）
        category: 消息类别（见 MESSAGE_CATEGORIES）
        detail: 细节文本（如任务数、新员工名）
        context: 给 LLM 的上下文描述
        router: 可选的 LLM router，None 则用模板降级

    Returns:
        成功发送返回消息文本，被冷却或失败返回 None
    """
    if agent is None or not getattr(agent, "_alive", False):
        return None
    if category not in MESSAGE_CATEGORIES:
        return None

    # 1. 检查冷却
    cfg = get_category_config(category)
    cooldown_sec = cfg.get("cooldown", 3600)
    if cooldown_sec > 0:
        last_ts = agent._active_msg_cooldowns.get(category, 0.0)
        if time.time() - last_ts < cooldown_sec:
            return None  # 还在冷却中

    # 2. 生成消息文本
    name = getattr(agent, "_name_obj", "?")
    species = getattr(agent, "species", "unknown")
    energy = getattr(agent, "energy", 50.0)
    health = getattr(agent, "health", 100.0)
    emo = getattr(agent, "emotional_state", {})
    top_e = max(emo.items(), key=lambda x: x[1])[0] if emo else "neutral"

    text = None
    # 优先尝试 LLM（如果传入了 router）
    if router is not None:
        prompt = build_llm_prompt(
            name, species, energy, health, top_e, category, context or detail
        )
        text = generate_via_llm(router, prompt)

    # LLM 失败或未传 router → 降级到模板
    if not text:
        text = pick_template(category, species, name, detail)

    # 3. 推送到 environment 的主动消息队列
    env = getattr(agent, "_environment", None)
    if env is None:
        return None
    ok = env.push_active_message(
        sender=name,
        sender_species=species,
        text=text,
        category=category,
        priority=cfg.get("priority", "low"),
    )
    if not ok:
        # 全局速率限制触发，未发送
        return None

    # commit 32：交给 MessageRouter 分发到外部渠道（桌面通知/微信/邮件等）
    # 失败不影响管控台消息队列（已入队），仅静默跳过
    try:
        from core.digital_life.message_router import dispatch_active_message

        dispatch_active_message(
            {
                "sender": name,
                "sender_species": species,
                "text": text,
                "category": category,
                "priority": cfg.get("priority", "low"),
                "time": time.time(),
            }
        )
    except Exception:
        pass

    # 4. 记录冷却
    agent._active_msg_cooldowns[category] = time.time()
    # 同时写入智能体短期记忆
    try:
        agent._remember(f"（向监工发送消息）{text}", importance="normal")
    except Exception:
        pass
    return text


# ====================================================================
# 触发条件检测函数（供 DigitalLifeForm.tick 调用）
# ====================================================================


def detect_and_trigger(agent: Any, router: Any = None) -> None:
    """扫描智能体状态，按需触发主动消息。

    在 DigitalLifeForm.tick 中每 60 秒调用一次。
    """
    if agent is None or not getattr(agent, "_alive", False):
        return
    if getattr(agent, "sleeping", False):
        return  # 睡觉时不发消息

    now = time.time()
    energy = getattr(agent, "energy", 100.0)
    health = getattr(agent, "health", 100.0)
    emo = getattr(agent, "emotional_state", {})
    anxiety = emo.get("anxiety", 0)
    sadness = emo.get("sadness", 0)

    # 1. 健康危机：能量 < 20 或健康 < 30
    if energy < 20 or health < 30:
        detail = f"能量{energy:.0f}/健康{health:.0f}"
        trigger_active_message(
            agent,
            "health_crisis",
            detail=detail,
            context=f"健康危机：{detail}",
            router=router,
        )
        return  # 危机期间不发其他消息

    # 2. 情绪波动：焦虑 > 0.8 或悲伤 > 0.7
    if anxiety > 0.8 or sadness > 0.7:
        detail = f"焦虑{anxiety:.2f}/悲伤{sadness:.2f}"
        trigger_active_message(
            agent,
            "emotion_distress",
            detail=detail,
            context=f"情绪波动：{detail}",
            router=router,
        )
        return

    # 3. 想念监工：距上次 fondness 衰减时间 > 3 天无互动
    #    用 _last_supervisor_interact_ts 字段（在 interact_* 中更新）
    last_interact = getattr(agent, "_last_supervisor_interact_ts", 0.0)
    if last_interact > 0 and now - last_interact > 3 * 86400:
        trigger_active_message(
            agent, "missing_supervisor", context="已 3 天未与监工互动", router=router
        )
        return

    # 4. 早安问候：每天早晨 7-9 点之间，且今天还没问候过
    hour = datetime.datetime.now().hour
    if 7 <= hour < 9:
        last_greet = agent._active_msg_cooldowns.get("morning_greeting", 0.0)
        # 同一天内不重复（用日期判断，而不是冷却时间）
        if last_greet > 0:
            last_dt = datetime.datetime.fromtimestamp(last_greet)
            now_dt = datetime.datetime.now()
            if last_dt.date() == now_dt.date():
                pass  # 今天已问候
            else:
                trigger_active_message(
                    agent, "morning_greeting", context="早安问候", router=router
                )
        else:
            trigger_active_message(
                agent, "morning_greeting", context="早安问候", router=router
            )
