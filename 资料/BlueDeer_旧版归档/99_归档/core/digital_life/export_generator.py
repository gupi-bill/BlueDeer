"""commit 40：对外分享与导出 - 卡片/快照/文案生成。

零基础读者可以这样理解：
- 想把某只智能体分享给朋友？生成一张精美的像素风格卡片（PNG）
- 想记录公司当前状态？导出一份 Markdown 快照
- 想发朋友圈？让 LLM 自动写一段温暖有趣的分享文案

零第三方依赖：
- PNG 卡片：返回 SVG（浏览器可直接预览/下载，前端 canvas 也能转 PNG）
- Markdown 快照：纯字符串拼接
- 分享文案：调 LLM，失败时降级用模板
"""

from __future__ import annotations

import time
from typing import Any

# ruff: noqa: S110, S112

# 物种主题色（与 game_frontend.py 的 SPECIES_COLORS 一致）
SPECIES_COLORS = {
    "deer": "#c9a96e",
    "squirrel": "#a87238",
    "butterfly": "#e8a8c8",
    "fox": "#e87048",
    "hedgehog": "#8a7a5a",
    "beaver": "#9a6840",
    "raven": "#3a3a4a",
    "hare": "#d8d8e0",
    "badger": "#6a5a4a",
    "lark": "#a8c8e0",
    "kite": "#7a8a9a",
}

# 物种中文名
SPECIES_CN = {
    "deer": "鹿",
    "squirrel": "松鼠",
    "butterfly": "蝴蝶",
    "fox": "狐狸",
    "hedgehog": "刺猬",
    "beaver": "海狸",
    "raven": "渡鸦",
    "hare": "野兔",
    "badger": "獾",
    "lark": "云雀",
    "kite": "鸢",
}

# 岗位描述
SPECIES_ROLE = {
    "deer": "团队领导·编排者",
    "squirrel": "工程师·代码编写",
    "butterfly": "设计师·UI 美化",
    "fox": "测试工程师·质量把关",
    "hedgehog": "安全工程师·漏洞防御",
    "beaver": "运维工程师·环境部署",
    "raven": "记忆管理员·资料归档",
    "hare": "数据分析师·性能统计",
    "badger": "网络工程师·接口维护",
    "lark": "监控工程师·告警观察",
    "kite": "调度工程师·任务排期",
}



def _build_avatar(species: str) -> str:
    """读取物种参考图并以 base64 内嵌到 SVG；失败返回空串。"""
    import base64 as _b64
    from pathlib import Path as _P
    chars = _P(__file__).resolve().parent.parent.parent / "static" / "assets" / "characters"
    img = chars / f"{species}.png"
    if not img.exists():
        return ""
    data = _b64.b64encode(img.read_bytes()).decode("ascii")
    return (
        '<image x="40" y="40" width="128" height="128" '
        'preserveAspectRatio="xMidYMid slice" '
        f'href="data:image/png;base64,{data}"/>'
    )


def _pinyin(name: str) -> str:
    """把中文名字粗略转拼音（只处理已知名字，未知的返回空）。"""
    PINYIN_MAP = {
        "鹿": "Lu",
        "忧郁": "Youyu",
        "鼠": "Shu",
        "栗壳": "Like",
        "蝶": "Die",
        "绘羽": "Huiyu",
        "狐": "Hu",
        "赤谋": "Chimou",
        "猬": "Wei",
        "针客": "Zhenke",
        "狸": "Li",
        "大坝": "Daba",
        "鸦": "Ya",
        "黑卷": "Heijuan",
        "兔": "Tu",
        "霜耳": "Shuanger",
        "獾": "Huan",
        "土工": "Tugong",
        "雀": "Que",
        "清音": "Qingyin",
        "鸢": "Yuan",
        "天瞰": "Tiankan",
    }
    # 名字格式："鹿·忧郁" → "Lu Youyu"
    parts = name.split("·")
    result = []
    for p in parts:
        if p in PINYIN_MAP:
            result.append(PINYIN_MAP[p])
    return " ".join(result) if result else ""


def _escape_svg(text: str) -> str:
    """转义 SVG 文本中的特殊字符。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_skill_items(skills: Any) -> str:
    skill_items = ""
    if isinstance(skills, list):
        for i, k in enumerate(skills[:6]):
            y = 280 + i * 22
            skill_items += f'<text x="40" y="{y}" font-size="14" fill="#aaa">★ {_escape_svg(str(k))}</text>'
    elif isinstance(skills, dict):
        for i, (k, v) in enumerate(list(skills.items())[:6]):
            y = 280 + i * 22
            level = int(v) if isinstance(v, (int, float)) else 0
            level_str = "★" * min(5, level) + "☆" * max(0, 5 - level)
            skill_items += f'<text x="40" y="{y}" font-size="14" fill="#aaa">{_escape_svg(k)}: {level_str}</text>'
    return skill_items


def _build_mutation_badge(mutations: list) -> str:
    if mutations:
        return f'<text x="380" y="120" font-size="20" fill="#ffd700">✨ 突变×{len(mutations)}</text>'
    return ""


def _build_role_badge(informal_roles: list) -> str:
    if informal_roles:
        role_text = "·".join(informal_roles[:2])
        return f'<text x="40" y="245" font-size="13" fill="#b488ff">🎭 {_escape_svg(role_text)}</text>'
    return ""


def generate_agent_card_svg(agent_dict: dict) -> str:
    """生成智能体分享卡片 SVG。

    Args:
        agent_dict: 智能体状态 dict，至少包含 name/species/age/health/skills

    Returns:
        SVG 字符串（前端可用 canvas 转换为 PNG 或直接下载）。
    """
    name = agent_dict.get("name", "")
    species = agent_dict.get("species", "")
    age = float(agent_dict.get("age", 0))
    health = float(agent_dict.get("health", 0))
    skills = agent_dict.get("skills", {})
    informal_roles = agent_dict.get("informal_roles", [])
    mutations = agent_dict.get("mutations", [])
    achievement = agent_dict.get("achievement", "")
    intro = agent_dict.get("intro", "")

    theme_color = SPECIES_COLORS.get(species, "#888")
    species_cn = SPECIES_CN.get(species, species)
    role_desc = SPECIES_ROLE.get(species, "")
    pinyin = _pinyin(name)

    skill_items = _build_skill_items(skills)
    mutation_badge = _build_mutation_badge(mutations)
    role_badge = _build_role_badge(informal_roles)
    avatar_image = _build_avatar(species)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="480" height="640" viewBox="0 0 480 640">
  <!-- 背景 -->
  <rect width="480" height="640" fill="#1a1a2e"/>
  <rect width="480" height="640" fill="{theme_color}" opacity="0.08"/>
  <!-- 像素边框 -->
  <rect x="8" y="8" width="464" height="624" fill="none" stroke="{theme_color}" stroke-width="3"/>
  <rect x="14" y="14" width="452" height="612" fill="none" stroke="{theme_color}" stroke-width="1" opacity="0.5"/>

  <!-- 头像区（128×128 像素方框） -->
  <rect x="40" y="40" width="128" height="128" fill="#000" opacity="0.3"/>
  <rect x="40" y="40" width="128" height="128" fill="none" stroke="{theme_color}" stroke-width="2"/>
  {avatar_image}

  <!-- 名字 -->
  <text x="180" y="80" font-size="28" font-weight="bold" fill="#fff" font-family="sans-serif">{_escape_svg(name)}</text>
  <text x="180" y="105" font-size="14" fill="#888" font-family="sans-serif">{_escape_svg(pinyin)}</text>
  <text x="180" y="130" font-size="14" fill="{theme_color}" font-family="sans-serif">{species_cn} · {_escape_svg(role_desc)}</text>
  <text x="180" y="155" font-size="12" fill="#aaa" font-family="sans-serif">年龄 {age:.1f} 天 · 健康 {health:.0f}</text>
  {mutation_badge}

  <!-- 分隔线 -->
  <line x1="40" y1="200" x2="440" y2="200" stroke="{theme_color}" stroke-width="1" opacity="0.4"/>

  <!-- 自我介绍 -->
  <text x="40" y="225" font-size="13" fill="#cdd6e6" font-family="sans-serif">{_escape_svg(intro or f"我是{name}，{species_cn}族的{role_desc}。")}</text>

  {role_badge}

  <!-- 技能列表标题 -->
  <text x="40" y="265" font-size="14" font-weight="bold" fill="{theme_color}" font-family="sans-serif">技能</text>
  {skill_items}

  <!-- 最骄傲的成就 -->
  <text x="40" y="430" font-size="14" font-weight="bold" fill="{theme_color}" font-family="sans-serif">最骄傲的成就</text>
  <text x="40" y="455" font-size="13" fill="#cdd6e6" font-family="sans-serif">{_escape_svg(achievement or "持续为公司贡献每一天")}</text>

  <!-- 入职日期 -->
  <text x="40" y="500" font-size="12" fill="#888" font-family="sans-serif">入职日期：{time.strftime("%Y-%m-%d", time.localtime(float(agent_dict.get("birth_ts", time.time()))))}</text>

  <!-- 底部 logo -->
  <line x1="40" y1="540" x2="440" y2="540" stroke="{theme_color}" stroke-width="1" opacity="0.4"/>
  <text x="240" y="580" font-size="16" fill="{theme_color}" text-anchor="middle" font-family="sans-serif" font-weight="bold">🌲 BlueDeer 森林公司</text>
  <text x="240" y="605" font-size="11" fill="#666" text-anchor="middle" font-family="sans-serif">https://github.com/bluedeer/forest</text>
</svg>"""


def _build_snapshot_header(now: str) -> list[str]:
    lines = []
    lines.append("# 🌲 BlueDeer 森林公司状态快照")
    lines.append("")
    lines.append(f"**导出时间**：{now}")
    lines.append("")
    return lines


def _build_supervisor_info(env: Any) -> list[str]:
    lines = []
    marks = float(getattr(env, "marks", 0.0))
    lines.append("## 监工档案")
    lines.append("")
    lines.append(f"- 森林印记余额：{marks:.0f}")
    lines.append("")
    return lines


def _build_employee_table(alive: list) -> list[str]:
    lines = []
    lines.append(f"## 当前员工（{len(alive)} 人）")
    lines.append("")
    lines.append("| 名字 | 物种 | 年龄 | 健康 | 情绪 | 岗位 |")
    lines.append("|------|------|------|------|------|------|")
    for lf in alive:
        name = getattr(lf, "_name_obj", "")
        species = getattr(lf, "species", "")
        try:
            age = float(getattr(lf, "age", 0))
        except Exception:
            age = 0.0
        try:
            health = float(getattr(lf, "health", 0))
        except Exception:
            health = 0.0
        try:
            mood = float(getattr(lf, "mood_score", 0.5))
        except Exception:
            mood = 0.5
        species_cn = SPECIES_CN.get(species, species)
        role = SPECIES_ROLE.get(species, "")
        lines.append(
            f"| {name} | {species_cn} | {age:.1f}天 | {health:.0f} | {mood:.2f} | {role} |"
        )
    lines.append("")
    return lines


def _build_skill_matrix(alive: list) -> list[str]:
    lines = []
    if not alive:
        return lines
    all_skills = set()
    for lf in alive:
        sk = getattr(lf, "skills", [])
        if isinstance(sk, list):
            all_skills.update(sk)
        elif isinstance(sk, dict):
            all_skills.update(sk.keys())
    all_skills = sorted(all_skills)[:10]
    if all_skills:
        lines.append("## 技能矩阵")
        lines.append("")
        header = "| 名字 | " + " | ".join(all_skills) + " |"
        sep = "|------|" + "|".join(["------"] * len(all_skills)) + "|"
        lines.append(header)
        lines.append(sep)
        for lf in alive:
            name = getattr(lf, "_name_obj", "")
            sk = getattr(lf, "skills", [])
            row = [name]
            for s in all_skills:
                if isinstance(sk, list):
                    row.append("✓" if s in sk else "-")
                elif isinstance(sk, dict):
                    v = sk.get(s, 0)
                    row.append(str(int(v)) if isinstance(v, (int, float)) else "-")
                else:
                    row.append("-")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    return lines


def _build_deceased_section(employees: list) -> list[str]:
    lines = []
    deceased = [lf for lf in employees if not getattr(lf, "_alive", False)]
    if deceased:
        lines.append(f"## 已故员工纪念（{len(deceased)} 位）")
        lines.append("")
        for lf in deceased:
            name = getattr(lf, "_name_obj", "")
            species = getattr(lf, "species", "")
            species_cn = SPECIES_CN.get(species, species)
            summary = getattr(lf, "life_summary", "") or "曾为公司默默奉献"
            lines.append(f"- **{name}**（{species_cn}）：{summary}")
        lines.append("")
    return lines


def _build_resources_section(env: Any) -> list[str]:
    lines = []
    if env:
        food = float(getattr(env, "food_available", 0.0))
        lines.append("## 资源状态")
        lines.append("")
        lines.append(f"- 食物资源：{food:.0f}")
        lines.append(f"- 森林印记：{float(getattr(env, 'marks', 0)):.0f}")
        lines.append("")
    return lines


def _build_events_section(env: Any) -> list[str]:
    lines = []
    event_log = getattr(env, "event_log", []) if env else []
    if event_log:
        month_ago = time.time() - 30 * 86400
        recent = []
        for e in event_log:
            try:
                t_val = float(e.get("time", 0)) if isinstance(e, dict) else 0
                if t_val > month_ago:
                    recent.append(e)
            except Exception as e:
                continue
        if recent:
            lines.append(f"## 本月关键事件（{len(recent)} 条）")
            lines.append("")
            for e in recent[-10:]:
                try:
                    t_val = float(e.get("time", 0)) if isinstance(e, dict) else 0
                    t = time.strftime("%m-%d %H:%M", time.localtime(t_val))
                    desc = (
                        e.get("description", e.get("desc", str(e)))
                        if isinstance(e, dict)
                        else str(e)
                    )
                    lines.append(f"- `{t}` {desc}")
                except Exception as e:
                    continue
            lines.append("")
    return lines


def _build_standup_section() -> list[str]:
    lines = []
    try:
        from core.digital_life.project_manager import ProjectManager

        pm = ProjectManager.get_instance()
        standups = pm.list_standups()
        if standups:
            latest = standups[-1]
            lines.append("## 今日站会摘要")
            lines.append("")
            lines.append(f"**日期**：{latest.get('date', '')}")
            lines.append("")
            for r in latest.get("reports", []):
                agent = r.get("agent", "")
                y = r.get("yesterday", "")
                t = r.get("today", "")
                b = r.get("blockers", "无")
                lines.append(f"- **{agent}**：昨天 {y}；今天 {t}；阻塞 {b}")
            lines.append("")
    except Exception:
        pass
    return lines


def generate_snapshot_markdown(biosphere: Any) -> str:
    """生成公司状态快照（Markdown 格式）。

    Args:
        biosphere: Biosphere 实例

    Returns:
        Markdown 字符串。
    """
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines: list[str] = []
    lines.extend(_build_snapshot_header(now))

    env = getattr(biosphere, "env", None)
    if env:
        lines.extend(_build_supervisor_info(env))

    employees = getattr(biosphere, "employees", [])
    alive = [lf for lf in employees if getattr(lf, "_alive", False)]
    lines.extend(_build_employee_table(alive))
    lines.extend(_build_skill_matrix(alive))
    lines.extend(_build_deceased_section(employees))

    if env:
        lines.extend(_build_resources_section(env))
        lines.extend(_build_events_section(env))

    lines.extend(_build_standup_section())

    lines.append("---")
    lines.append("*由 BlueDeer 森林公司自动生成*")
    return "\n".join(lines)


def generate_share_text(biosphere: Any, router: Any = None) -> str:
    """生成分享文案。

    Args:
        biosphere: Biosphere 实例
        router: LLM router（可选，不可用时降级用模板）

    Returns:
        分享文案字符串。
    """
    employees = getattr(biosphere, "employees", [])
    alive = [lf for lf in employees if getattr(lf, "_alive", False)]
    deer = next((lf for lf in alive if lf.species == "deer"), None)
    squirrel = next((lf for lf in alive if lf.species == "squirrel"), None)
    raven = next((lf for lf in alive if lf.species == "raven"), None)
    fox = next((lf for lf in alive if lf.species == "fox"), None)

    deer_name = getattr(deer, "_name_obj", "鹿") if deer else "鹿"
    sq_name = getattr(squirrel, "_name_obj", "松鼠") if squirrel else "松鼠"
    raven_name = getattr(raven, "_name_obj", "渡鸦") if raven else "渡鸦"
    fox_name = getattr(fox, "_name_obj", "狐狸") if fox else "狐狸"

    # 计算公司运行天数（用 deer 的年龄近似）
    run_days = int(float(getattr(deer, "age", 0))) if deer else 0
    # 统计已故员工
    deceased_count = len([lf for lf in employees if not getattr(lf, "_alive", False)])

    # 模板文案
    template = (
        f"我的数字森林公司已经运行 {run_days} 天了！"
        f"🦌 {deer_name} 领导着 {len(alive) - 1} 位动物员工，"
        f"{sq_name} 写了无数段代码，"
        f"{raven_name} 收藏了 {deceased_count} 个已故同事的记忆。"
        f"{fox_name} 每天毒舌但从未真的生气过。"
        f"欢迎来参观 → [链接]"
    )

    if router is None:
        return template

    # 尝试调 LLM 生成更有趣的文案
    try:
        import asyncio

        prompt = (
            f"你是 BlueDeer 森林公司的故事讲述者。"
            f"用户的数字森林公司已经运行 {run_days} 天了，"
            f"现在有 {len(alive)} 位活着的动物员工和 {deceased_count} 位已故员工。"
            f"团队领导是 {deer_name}（鹿），代码工程师是 {sq_name}（松鼠），"
            f"测试工程师是 {fox_name}（狐狸，性格毒舌），记忆管理员是 {raven_name}（渡鸦）。\n"
            f"请用 100 字以内写一段温暖、有趣的分享文案，"
            f"突出每个用户森林公司的独特性，结尾邀请朋友来参观。"
        )
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(router.complete(prompt))
        finally:
            loop.close()
        text = str(response).strip() if response else ""
        return text if text else template
    except Exception:
        return template


def get_export_generator():
    """获取模块级单例（这个模块本身无状态，返回模块即可）。"""
    return  # 所有函数都是无状态的，不需要单例
