"""ReAct 循环：模型每轮只出一个动作，代码执行工具并把观察喂回去。"""

import hashlib
import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

FINAL_RE = re.compile(r"^\s*FINAL\s*[:：]\s*(.*)$", re.S | re.I)
TOOL_RE = re.compile(r"^\s*TOOL\s*[:：]\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.I)
ARGS_RE = re.compile(r"^\s*ARGS\s*[:：]\s*(\{.*\})\s*$", re.S)


def append_jsonl(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("[loop] 记忆落盘失败: %s", e)


def load_recent(path: Path, n: int = 4) -> list[dict]:
    if not path.exists() or n <= 0:
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


class AgentLoop:
    def __init__(self, provider, tools: dict, cfg: dict):
        self.provider = provider
        self.tools = tools
        self.max_steps = int(cfg.get("max_steps", 8))
        self.memory_file = Path(cfg.get("memory_file", "data/agent_memory.jsonl"))
        if not self.memory_file.is_absolute():
            from bluedeer.config import ROOT_DIR
            self.memory_file = ROOT_DIR / self.memory_file
        self.memory_turns = int(cfg.get("memory_turns", 4))

    def _transcript(self, system: str, task: str, steps: list[dict]) -> str:
        from bluedeer.tools import catalog

        rules = (
            "你是一个能使用工具的智能体。每一轮你只能输出以下两种格式之一，不要输出其他内容：\n"
            'TOOL: 工具名\nARGS: {json 参数}\n'
            "或者当你已有足够信息给出最终答案时：\nFINAL: 最终回答"
        )
        parts = []
        if system:
            parts.append(f"[系统]\n{system}")
        parts.append(f"[可用工具]\n{catalog(self.tools)}")
        parts.append(f"[格式规则]\n{rules}")
        history = load_recent(self.memory_file, self.memory_turns)
        for i, h in enumerate(history, 1):
            parts.append(f"[历史对话 {i}]\n用户：{h.get('input', '')}\n助手：{h.get('output', '')}")
        parts.append(f"[任务]\n{task}")
        for s in steps:
            if s["type"] == "tool":
                parts.append(f"[步骤 {s['step']}]\nTOOL: {s['tool']}\nARGS: {json.dumps(s['args'], ensure_ascii=False)}\nObservation: {s['observation']}")
            else:
                parts.append(f"[步骤 {s['step']}]\n（上轮输出无效）\nObservation: {s['observation']}")
        parts.append("[现在轮到你] 请输出 TOOL/ARGS 或 FINAL。")
        return "\n\n".join(parts)

    def run(self, task: str, system: str = "") -> tuple[str, list[dict], str]:
        steps: list[dict] = []
        seen_hashes: set[str] = set()
        tool_calls = 0
        stop_reason = ""

        for step in range(1, self.max_steps + 1):
            reply = self.provider.generate(self._transcript(system, task, steps), None, system=None)
            final_m = FINAL_RE.search(reply)
            if final_m and not TOOL_RE.search(reply.splitlines()[0] if reply.strip() else ""):
                output = final_m.group(1).strip()
                stop_reason = "success"
                break
            tool_name = ""
            args_raw = "{}"
            for line in reply.strip().splitlines():
                m = TOOL_RE.match(line)
                if m:
                    tool_name = m.group(1)
                    continue
                m = ARGS_RE.match(line)
                if m:
                    args_raw = m.group(1)
            if not tool_name or tool_name not in self.tools:
                observation = f"[错误] 无效动作：没有名为 '{tool_name}' 的工具。请严格按 TOOL:/ARGS: 格式重新输出。"
                steps.append({"step": step, "type": "invalid", "tool": tool_name, "args": {}, "observation": observation})
                continue
            try:
                args = json.loads(args_raw)
                if not isinstance(args, dict):
                    raise ValueError("ARGS 必须是 json 对象")
            except Exception as e:
                observation = f"[错误] ARGS 解析失败：{e}，原始内容：{args_raw[:200]}"
                steps.append({"step": step, "type": "tool", "tool": tool_name, "args": {}, "observation": observation})
                continue
            h = hashlib.md5(f"{tool_name}|{json.dumps(args, sort_keys=True, ensure_ascii=False)}".encode()).hexdigest()
            if h in seen_hashes:
                stop_reason = "loop_detected"
                break
            seen_hashes.add(h)
            tool_calls += 1
            observation = self.tools[tool_name].func(args)
            log.info("[loop] step=%s tool=%s -> %s", step, tool_name, observation[:80])
            steps.append({"step": step, "type": "tool", "tool": tool_name, "args": args, "observation": observation})
        else:
            stop_reason = "max_steps"

        if not stop_reason:
            stop_reason = "max_steps"
        if stop_reason == "success":
            output_text = output
        elif stop_reason == "loop_detected":
            output_text = f"[停止] 检测到重复调用同一工具相同参数，已中止。已执行 {len(steps)} 步。"
        elif tool_calls >= 8:
            output_text = f"[停止] 达到最大工具调用次数。已执行 {len(steps)} 步。"
            stop_reason = "max_tool_calls"
        else:
            last_obs = steps[-1]["observation"] if steps else "（无）"
            output_text = f"[停止] 达到最大步数（{self.max_steps}）。最后的观察：{last_obs[:300]}"

        record = {"ts": time.time(), "input": task, "output": output_text, "steps": len(steps), "stop_reason": stop_reason}
        append_jsonl(self.memory_file, record)
        return output_text, steps, stop_reason


def run_loop(provider, tools: dict, task: str, system: str, cfg: dict, ctx=None) -> str:
    loop = AgentLoop(provider, tools, cfg)
    output, steps, stop_reason = loop.run(task, system)
    if ctx is not None:
        ctx.metadata["steps"] = steps
        ctx.metadata["stop_reason"] = stop_reason
    return output
