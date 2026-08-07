"""commit 38：执行后反思（复盘）。

零基础读者可以这样理解：
- 智能体做完一件事后，回头想想：做得怎么样？哪里顺利、哪里卡壳？
- 复盘产出的"经验"会存进经验库，下次同类任务会自动注入参考
- LLM 不可用时走"模板降级"——按物种生成固定句式的经验

存储路径：data/retrospects.json
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import threading
import time
import uuid
from typing import Any

# ----------------------------------------------------------------------
# 存储路径
# ----------------------------------------------------------------------

_RETROSPECT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "retrospects.json",
)


# ----------------------------------------------------------------------
# LLM Prompt
# ----------------------------------------------------------------------

RETRO_PROMPT_TEMPLATE = """你是 BlueDeer 森林公司的{species_zh}（{agent_name}），刚完成一个任务。
请对这次任务进行复盘，输出严格按以下格式：

任务描述：{task}
执行结果：{result_str}
耗时：{duration_sec:.1f} 秒
工具调用次数：{tool_count}
采用的历史经验：{exp_str}

请用以下三段式输出（每段一行，不要其他文字）：
LESSON: <一句话学到的经验，下次同类任务可以复用的>
SUMMARY: <一句话总结这次执行过程>
IMPROVEMENT: <一句话改进建议，下次如何做得更好>

注意：
- LESSON 必须是"可复用的经验"，不是过程描述
- 例如："涉及安全的模块应优先考虑加密逻辑，不能等测试才发现"
- 例如："模糊测试前先检查输入生成器的边界覆盖"
"""


# ----------------------------------------------------------------------
# 物种中文名（与 agent_function_calling 一致）
# ----------------------------------------------------------------------

_SPECIES_ZH: dict[str, str] = {
    "deer": "鹿·忧郁",
    "squirrel": "鼠·栗壳",
    "butterfly": "蝶·绘羽",
    "fox": "狐·赤谋",
    "hedgehog": "猬·针客",
    "beaver": "狸·大坝",
    "raven": "鸦·黑卷",
    "hare": "兔·霜耳",
    "badger": "獾·土工",
    "lark": "雀·清音",
    "kite": "鸢·天瞰",
}


# ----------------------------------------------------------------------
# 物种默认经验模板（LLM 不可用时降级用）
# ----------------------------------------------------------------------

_SPECIES_LESSON_TEMPLATE: dict[str, list[str]] = {
    "squirrel": [
        "代码生成完成后先自查边界条件和异常处理，再交给测试",
        "涉及安全的模块应优先考虑加密/哈希逻辑",
        "复杂算法先列思路再写实现，避免中途返工",
    ],
    "butterfly": [
        "UI 设计先确认布局结构再调样式，减少返工",
        "交互反馈要考虑用户等待心理，长操作需加载态",
    ],
    "fox": [
        "测试用例覆盖正常路径 + 边界 + 异常三类",
        "模糊测试前先检查输入生成器的覆盖度",
    ],
    "hedgehog": [
        "安全扫描先看高危项再看中危，按优先级处理",
        "证书和密钥管理要分离存储，避免硬编码",
    ],
    "beaver": [
        "部署前先确认环境变量和配置文件一致性",
        "存储事务要测试回滚路径，不能只测提交",
    ],
    "raven": [
        "检索召回率优先于精确率，先广后筛",
        "向量索引构建时注意维度对齐",
    ],
    "hare": [
        "统计分析先检查数据完整性再下结论",
        "异常检测要标注置信度，避免误报",
    ],
    "badger": [
        "网络接口调试先看响应头再看响应体",
        "WebSocket 长连接要测试断线重连",
    ],
    "lark": [
        "监控指标先定基线再设告警阈值",
        "告警分级处理，避免噪声淹没真问题",
    ],
    "kite": [
        "调度规划先列约束再求最优解",
        "关键路径上的任务要预留缓冲时间",
    ],
    "deer": [
        "任务编排先拆解再分配，每步明确产出",
        "汇总报告要包含执行摘要 + 详细数据 + 风险点",
    ],
}


# ----------------------------------------------------------------------
# 复盘生成
# ----------------------------------------------------------------------

_lock = threading.RLock()


def generate_retrospect(
    agent_species: str,
    agent_name: str,
    task: str,
    tool_calls: list,
    result_ok: bool,
    duration_sec: float,
    experience_adopted: list | None = None,
    router: Any = None,
) -> dict:
    """生成一次任务的复盘。

    Args:
        agent_species: 物种代号
        agent_name: 显示名
        task: 任务文本
        tool_calls: 工具调用记录 list[dict]
        result_ok: 任务是否成功
        duration_sec: 耗时秒数
        experience_adopted: 本次采用的历史经验 list[str]
        router: LLM 路由器；None 时走模板降级

    Returns:
        {"id", "agent_species", "agent_name", "task", "lesson",
         "summary", "improvement", "ok", "duration_sec",
         "tool_call_count", "task_type", "ts"}
    """
    experience_adopted = experience_adopted or []
    tool_count = len(tool_calls or [])

    # 尝试 LLM 复盘
    lesson = ""
    summary = ""
    improvement = ""
    used_llm = False
    if router is not None:
        try:
            text = _call_llm_for_retrospect(
                router,
                agent_species,
                agent_name,
                task,
                result_ok,
                duration_sec,
                tool_count,
                experience_adopted,
            )
            parsed = _parse_retrospect_output(text)
            if parsed["lesson"]:
                lesson = parsed["lesson"]
                summary = parsed["summary"]
                improvement = parsed["improvement"]
                used_llm = True
        except Exception:
            pass

    # 模板降级
    if not lesson:
        lesson = _template_lesson(agent_species, result_ok)
        summary = _template_summary(agent_species, task, result_ok, duration_sec)
        improvement = _template_improvement(agent_species, result_ok)

    # 任务类型分类
    try:
        from core.digital_life.experience_library import classify_task_type

        task_type = classify_task_type(task)
    except Exception:
        task_type = "其他"

    retro = {
        "id": "retro-" + uuid.uuid4().hex[:8],
        "agent_species": agent_species,
        "agent_name": agent_name,
        "task": (task or "")[:200],
        "lesson": lesson,
        "summary": summary,
        "improvement": improvement,
        "ok": bool(result_ok),
        "duration_sec": round(duration_sec, 2),
        "tool_call_count": tool_count,
        "task_type": task_type,
        "used_llm": used_llm,
        "ts": time.time(),
    }

    # 持久化
    _save_retrospect(retro)

    # 写入经验库
    if lesson:
        try:
            from core.digital_life.experience_library import get_experience_library

            get_experience_library().add_experience(
                agent_species=agent_species,
                task_summary=task,
                lesson=lesson,
                task_type=task_type,
                improvement=improvement,
            )
        except Exception:
            pass

    return retro


# ----------------------------------------------------------------------
# LLM 调用
# ----------------------------------------------------------------------


def _call_llm_for_retrospect(
    router,
    agent_species: str,
    agent_name: str,
    task: str,
    result_ok: bool,
    duration_sec: float,
    tool_count: int,
    experience_adopted: list,
) -> str:
    """调 LLM 生成复盘文本。"""
    species_zh = _SPECIES_ZH.get(agent_species, agent_species)
    exp_str = "、".join(experience_adopted) if experience_adopted else "无"
    prompt = RETRO_PROMPT_TEMPLATE.format(
        species_zh=species_zh,
        agent_name=agent_name or species_zh,
        task=(task or "")[:200],
        result_str="成功" if result_ok else "失败",
        duration_sec=duration_sec,
        tool_count=tool_count,
        exp_str=exp_str,
    )

    loop = asyncio.new_event_loop()
    try:
        resp = loop.run_until_complete(
            router.complete_with_failover(
                task_type="reasoning",
                prompt=prompt,
                agent_id=f"retrospect-{agent_species}",
            )
        )
        return getattr(resp, "content", "") or ""
    finally:
        loop.close()


def _parse_retrospect_output(text: str) -> dict:
    """解析 LLM 输出的 LESSON/SUMMARY/IMPROVEMENT 三段。"""
    lesson = ""
    summary = ""
    improvement = ""

    # 用正则匹配每行
    m = re.search(r"LESSON\s*[:：]\s*(.+?)(?=\n|$)", text, re.IGNORECASE)
    if m:
        lesson = m.group(1).strip()
    m = re.search(r"SUMMARY\s*[:：]\s*(.+?)(?=\n|$)", text, re.IGNORECASE)
    if m:
        summary = m.group(1).strip()
    m = re.search(r"IMPROVEMENT\s*[:：]\s*(.+?)(?=\n|$)", text, re.IGNORECASE)
    if m:
        improvement = m.group(1).strip()

    return {"lesson": lesson, "summary": summary, "improvement": improvement}


# ----------------------------------------------------------------------
# 模板降级
# ----------------------------------------------------------------------


def _template_lesson(species: str, ok: bool) -> str:
    """LLM 不可用时的模板经验。"""
    templates = _SPECIES_LESSON_TEMPLATE.get(
        species,
        [
            "完成任务后及时记录关键决策点，便于复盘",
        ],
    )
    if ok:
        return templates[0]
    return f"任务失败，下次需检查：{templates[0] if '检查' in templates[0] else templates[-1]}"


def _template_summary(species: str, task: str, ok: bool, duration_sec: float) -> str:
    species_zh = _SPECIES_ZH.get(species, species)
    status = "成功完成" if ok else "执行失败"
    return f"{species_zh}用 {duration_sec:.1f} 秒{status}了「{(task or '')[:30]}」"


def _template_improvement(species: str, ok: bool) -> str:
    if ok:
        return "执行流程顺畅，下次同类任务可参考本次步骤"
    return "下次执行前先检查前置条件和资源是否就绪"


# ----------------------------------------------------------------------
# 持久化
# ----------------------------------------------------------------------


def _save_retrospect(retro: dict) -> None:
    """追加保存复盘记录。"""
    with _lock:
        try:
            os.makedirs(os.path.dirname(_RETROSPECT_PATH), exist_ok=True)
            data: dict = {"retrospects": []}
            if os.path.exists(_RETROSPECT_PATH):
                try:
                    with open(_RETROSPECT_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    data = {"retrospects": []}
            retros = data.get("retrospects", []) or []
            retros.append(retro)
            # 上限 500 条
            if len(retros) > 500:
                retros = retros[-500:]
            data["retrospects"] = retros
            with open(_RETROSPECT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def list_retrospects(agent_species: str = "", limit: int = 50) -> list[dict]:
    """列出复盘记录（按时间倒序）。"""
    with _lock:
        try:
            if not os.path.exists(_RETROSPECT_PATH):
                return []
            with open(_RETROSPECT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            retros = data.get("retrospects", []) or []
            if agent_species:
                retros = [r for r in retros if r.get("agent_species") == agent_species]
            retros.sort(key=lambda x: x.get("ts", 0), reverse=True)
            return retros[:limit]
        except (json.JSONDecodeError, OSError):
            return []


def get_retrospect(retro_id: str) -> dict | None:
    """按 ID 取单条复盘。"""
    with _lock:
        try:
            if not os.path.exists(_RETROSPECT_PATH):
                return None
            with open(_RETROSPECT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for r in data.get("retrospects", []) or []:
                if r.get("id") == retro_id:
                    return r
        except (json.JSONDecodeError, OSError):
            pass
        return None


# ----------------------------------------------------------------------
# 经验效果评估
# ----------------------------------------------------------------------


def evaluate_experience_outcome(prev_ok_rate: float, current_ok: bool) -> bool:
    """判断采用经验后效果是否更好。

    用 prev_ok_rate 做贝叶斯平滑：如果历史成功率已 > 0.7 且本次仍成功，
    说明经验稳健；如果历史成功率低但本次成功，说明有改进。

    Args:
        prev_ok_rate: 该经验历史上的成功率（0~1）
        current_ok: 本次任务是否成功

    Returns:
        better: True=权重 +1，False=权重 -1
    """
    if not current_ok:
        return False
    return prev_ok_rate >= 0.5 or random.random() < 0.3
