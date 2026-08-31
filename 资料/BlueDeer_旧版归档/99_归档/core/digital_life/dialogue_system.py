"""对话与内心独白系统。

零基础读者可以这样理解：
- 每个物种有自己的"口头禅"和"内心独白"语料库
- 当两个智能体靠近时，按物种对+情感+关系选一句对话
- 当智能体独处时，每小时 10% 概率产生一句内心独白
- 老年时设置"退休愿望"，死后留下"遗物"

所有语料都是中文短句，保证零基础可读。
"""

from __future__ import annotations

import random

# ====================================================================
# 对话语料库（按物种对分类）
# 键格式："sp1-sp2"（已排序），值是 (说话者物种, 文本) 列表
# ====================================================================

DIALOGUE_LIBRARY: dict[str, list[tuple[str, str]]] = {
    # 鹿 + 雀（调度官 + 监控官）
    "deer-lark": [
        ("deer", "状态怎么样？"),
        ("lark", "全绿，鹿总。"),
        ("deer", "辛苦了，注意休息。"),
        ("lark", "您也一样，鹿总。"),
    ],
    # 鹿 + 鸦（调度官 + 史官，智者同盟）
    "deer-raven": [
        ("raven", "老海狸·初代如果在世，今天该 15 岁了。"),
        ("deer", "它修的坝，海狸还在用。"),
        ("raven", "我替所有人记得，这是我的工作。"),
        ("deer", "那就拜托你了，渡鸦。"),
    ],
    # 松鼠 + 狐狸（藏坚果 + 抓 bug，天生欢喜冤家）
    "fox-squirrel": [
        ("squirrel", "别看我的代码！"),
        ("fox", "已经看完了，第三行少个分号。"),
        ("squirrel", "……我藏的坚果你别动。"),
        ("fox", "放心，我只对 bug 感兴趣。"),
    ],
    # 獾 + 蝶（地道工程师 + 花房管理员）
    "badger-butterfly": [
        ("badger", "花房湿度需要调吗？"),
        ("butterfly", "刚刚好，谢谢你。"),
        ("badger", "地道新支线快挖通了。"),
        ("butterfly", "回头我去给你送点花粉。"),
    ],
    # 海狸 + 鸢（修坝的 + 天上侦察的）
    "beaver-kite": [
        ("kite", "上游水情正常，可以放心筑坝。"),
        ("beaver", "辛苦你盯着，我加一层。"),
        ("kite", "下游有涨水迹象，建议加固。"),
        ("beaver", "收到，我马上加固。"),
    ],
    # 兔 + 雀（算账的 + 唱歌的）
    "hare-lark": [
        ("hare", "Token 还够用 47 天。除非来个大项目。"),
        ("lark", "那我就放心唱了。"),
        ("hare", "你唱吧，我算账。"),
    ],
    # 猬 + 鹿（巡视的 + 调度的）
    "deer-hedgehog": [
        ("hedgehog", "巡视完毕，没有异常。"),
        ("deer", "辛苦，回去歇歇。"),
    ],
    # 通用：相遇时的礼貌招呼（无特定配对时用）
    "_generic": [
        ("", "嗯。"),
        ("", "早。"),
        ("", "在忙？"),
        ("", "辛苦。"),
    ],
}


# ====================================================================
# 内心独白语料库（按物种 + 情感倾向分类）
# 每个物种有 neutral / happy / sad / anxious 四类
# ====================================================================

MONOLOGUE_LIBRARY: dict[str, dict[str, list[str]]] = {
    "deer": {
        "neutral": [
            "今天调度了 12 个任务，没有阻塞。不错。",
            "鹿角的光点又亮了，该是有人想起了我。",
        ],
        "happy": ["今天一切顺利，可以早点收工。"],
        "sad": ["老朋友的角，我又在夜里看见了。"],
        "anxious": ["任务积压了……得重新排一下优先级。"],
    },
    "squirrel": {
        "neutral": [
            "那颗上个月藏的坚果到底在哪儿……",
            "今天编译又通过了三个，尾巴可以松一下了。",
        ],
        "happy": ["嘿！这段代码我自己都觉得漂亮。"],
        "sad": ["藏的坚果找不到了，难过。"],
        "anxious": ["编译又红了，是不是我又写错分号了？"],
    },
    "butterfly": {
        "neutral": ["花房今天的湿度刚刚好。", "鳞粉又落了一点，没关系。"],
        "happy": ["阳光照进花房，一切都亮晶晶的。"],
        "sad": ["翅膀有点沉，是不是要下雨了。"],
        "anxious": ["花房温度异常，得赶紧看看。"],
    },
    "fox": {
        "neutral": ["九条尾巴，今天只用三条就够。", "松鼠的代码……我先不评价。"],
        "happy": ["今天抓了三个 bug，九尾都开心。"],
        "sad": ["老朋友越来越少……尾巴都收起来了。"],
        "anxious": ["松鼠又在改我的代码，盯紧点。"],
    },
    "hedgehog": {
        "neutral": ["巡视一圈，没有异常。", "刺又硬了一圈，安全。"],
        "happy": ["今天没有入侵者，可以缩一会儿。"],
        "sad": ["一个人太久，刺都生锈了。"],
        "anxious": ["有动静！等等，是我自己。"],
    },
    "beaver": {
        "neutral": ["坝又补了一层，今天可以睡个好觉。", "门牙又磨短了一点，没事。"],
        "happy": ["坝修得稳稳的，水流也听话。"],
        "sad": ["老坝又漏了，得重修。"],
        "anxious": ["水位上涨，得加高 30%。"],
    },
    "raven": {
        "neutral": [
            "老海狸·初代如果在世，今天该 15 岁了。",
            "我替所有人记得，这是我的工作。",
        ],
        "happy": ["今天的故事，孩子们都爱听。"],
        "sad": ["又送走了一位老朋友。"],
        "anxious": ["右眼模糊了……是记忆碎片飘得太多。"],
    },
    "hare": {
        "neutral": ["Token 还够用 47 天。除非来个大项目。", "耳朵算盘又打了一遍。"],
        "happy": ["账目平了，可以睡一会儿。"],
        "sad": ["老算盘珠子又丢了一颗。"],
        "anxious": ["预算超支了……得重新算。"],
    },
    "badger": {
        "neutral": ["地道新支线挖了一米。", "爪子又磨亮了一点。"],
        "happy": ["地道挖通了，可以直通花房。"],
        "sad": ["老地道塌了，得重挖。"],
        "anxious": ["地质有变动，得加固。"],
    },
    "lark": {
        "neutral": ["今天唱了三段，嗓音还稳。", "树枝又粗了一寸。"],
        "happy": ["尾羽今天是鹅黄色，负载很轻。"],
        "sad": ["尾羽红了……大家都很忙。"],
        "anxious": ["负载飙升，得赶紧报警。"],
    },
    "kite": {
        "neutral": ["高空盘旋三圈，一切正常。", "翼尖气流稳定。"],
        "happy": ["今天风很好，可以多飞一会儿。"],
        "sad": ["再也看不见那位老朋友了。"],
        "anxious": ["气流异常，得低空盘旋。"],
    },
    "overseer": {
        "neutral": ["今天 11 名员工都到岗了。", "平板电量还有 60%。"],
        "happy": ["这帮小家伙今天表现不错。"],
        "sad": ["又送走了一位，心里不好受。"],
        "anxious": ["任务积压了，得调整一下。"],
    },
}


# ====================================================================
# 退休愿望（每个物种一句）
# ====================================================================

RETIREMENT_WISHES: dict[str, str] = {
    "deer": "想在天井下静静看一天星星。",
    "squirrel": "想写完最后一段完美的代码。",
    "butterfly": "想在花房里跳最后一支舞。",
    "fox": "想把九条尾巴的故事都讲完。",
    "hedgehog": "想缩成球，在阳光下睡一整天。",
    "beaver": "想筑一座不用再修的完美水坝。",
    "raven": "想讲完所有记得的故事。",
    "hare": "想把账本算到分毫不差。",
    "badger": "想挖一条通向花房的地道。",
    "lark": "想唱一首不用看负载的歌。",
    "kite": "想在最高的天空盘旋最后一次。",
}


# ====================================================================
# 遗物（每个物种一件物理遗物 + 描述）
# ====================================================================

RELIC_DEFS: dict[str, dict] = {
    "deer": {
        "name": "脱落的鹿角碎片",
        "desc": "一小块脱落的鹿角，上面还残留着淡蓝光痕。",
    },
    "squirrel": {
        "name": "代码坚果",
        "desc": "一颗从未被找到的坚果，刻着一段完美代码。",
    },
    "butterfly": {
        "name": "鳞粉翅膀残片",
        "desc": "一片最美的翅膀鳞粉，阳光下泛着结构色。",
    },
    "fox": {"name": "机械尾尖零件", "desc": "九尾中一根的尾尖微零件，表面有微光残留。"},
    "hedgehog": {"name": "额头装甲片", "desc": "一块矩形装甲板，已褪去警戒的红色。"},
    "beaver": {"name": "门牙磨片", "desc": "一颗磨损的钛白门牙，曾啃过无数光缆。"},
    "raven": {"name": "银白羽毛", "desc": "一根异色瞳渡鸦的羽毛，右眼那侧的银白色。"},
    "hare": {"name": "算盘珠", "desc": "一颗耳朵上的微红算盘珠，曾记满 Token 账。"},
    "badger": {"name": "USB-C 接口爪", "desc": "前爪化的接口零件，亮银色已黯淡。"},
    "lark": {"name": "变色彩羽", "desc": "一根尾羽，颜色定格在暗红那一刻。"},
    "kite": {"name": "V 形尾羽", "desc": "一片分叉的尾羽，翼尖深靛蓝。"},
}


# ====================================================================
# 关系标签触发阈值
# ====================================================================

RELATIONSHIP_TAGS = {
    "挚友": {"affection": 0.8, "trust": 0.7},
    "搭档": {"trust": 0.8, "familiarity": 0.9},
    "导师": {"respect": 0.8},
}


# ====================================================================
# 工具函数
# ====================================================================


def pick_dialogue(
    sp1: str, sp2: str, emotion: dict | None = None, relationship: dict | None = None
) -> tuple[str, str] | None:
    """按物种对选一句对话。

    Args:
        sp1: 说话者物种
        sp2: 听话者物种
        emotion: 说话者情感状态（可选，影响选词）
        relationship: 关系 dict（可选，好友间更随意）

    Returns:
        (实际说话者物种, 文本)；无匹配返回 None。
    """
    key = "-".join(sorted([sp1, sp2]))
    candidates = DIALOGUE_LIBRARY.get(key) or DIALOGUE_LIBRARY.get("_generic")
    if not candidates:
        return None
    # 过滤：候选人中只挑符合说话者的（如果是 generic 则任意）
    sp1_options = [c for c in candidates if c[0] == sp1]
    sp2_options = [c for c in candidates if c[0] == sp2]
    pool = sp1_options or sp2_options or candidates
    return random.choice(pool)


def pick_monologue(species: str, emotion: dict | None = None) -> str:
    """按物种+情感选一句内心独白。

    情感倾向判定：
    - joy > 0.7 → happy
    - sadness > 0.6 → sad
    - anxiety > 0.7 → anxious
    - 其他 → neutral
    """
    lib = MONOLOGUE_LIBRARY.get(species) or MONOLOGUE_LIBRARY.get("overseer", {})
    mood_key = "neutral"
    if emotion:
        if emotion.get("joy", 0) > 0.7:
            mood_key = "happy"
        elif emotion.get("sadness", 0) > 0.6:
            mood_key = "sad"
        elif emotion.get("anxiety", 0) > 0.7:
            mood_key = "anxious"
    pool = lib.get(mood_key) or lib.get("neutral") or ["……"]
    return random.choice(pool)


def get_retirement_wish(species: str) -> str:
    """获取物种的退休愿望。"""
    return RETIREMENT_WISHES.get(species, "想静静地离开。")


def get_relic_def(species: str) -> dict:
    """获取物种的遗物定义。"""
    return RELIC_DEFS.get(species, {"name": "一件小遗物", "desc": "主人的痕迹。"})


def check_relationship_tags(rel: dict) -> list[str]:
    """根据关系值检测应打的标签。

    Args:
        rel: {affection/trust/respect/familiarity: float 0~1}

    Returns:
        标签列表（可能为空）。包含：挚友/搭档/导师/单恋
    """
    tags: list[str] = []
    for tag, thresholds in RELATIONSHIP_TAGS.items():
        if all(rel.get(k, 0) >= v for k, v in thresholds.items()):
            tags.append(tag)
    # 单恋：affection > 0.7 但 trust < 0.3（一方热情另一方冷淡）
    if rel.get("affection", 0) > 0.7 and rel.get("trust", 0) < 0.3:
        tags.append("单恋")
    return tags
