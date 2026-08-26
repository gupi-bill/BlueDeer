"""AgentLoop / tools 测试：脚本化 Provider 驱动 ReAct 循环。"""

import json
import tempfile
import unittest
from pathlib import Path

from bluedeer.loop import AgentLoop
from bluedeer.tools import build_tools


class ScriptedProvider:
    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, text, context=None, system=None):
        self.calls.append(text)
        return self.replies.pop(0) if self.replies else "FINAL: 没词了"


def make_cfg(tmp: Path, **kw):
    cfg = {
        "max_steps": kw.get("max_steps", 8),
        "memory_file": str(tmp / "mem.jsonl"),
        "memory_turns": kw.get("memory_turns", 4),
    }
    cfg.update({k: v for k, v in kw.items() if k not in ("max_steps", "memory_turns")})
    return cfg


class LoopTest(unittest.TestCase):
    def test_tool_call_then_final(self):
        tmp = Path(tempfile.mkdtemp())
        p = ScriptedProvider(['TOOL: calc\nARGS: {"expression": "1+2"}', "FINAL: 答案是3"])
        loop = AgentLoop(p, build_tools(["calc"]), make_cfg(tmp))
        out, steps, stop = loop.run("算一下1+2")
        self.assertEqual(out, "答案是3")
        self.assertEqual(stop, "success")
        self.assertEqual(len(steps), 1)
        self.assertIn("3", steps[0]["observation"])
        mem = (tmp / "mem.jsonl").read_text(encoding="utf-8").strip()
        rec = json.loads(mem)
        self.assertEqual(rec["stop_reason"], "success")

    def test_budget_stop(self):
        tmp = Path(tempfile.mkdtemp())
        p = ScriptedProvider([
            f'TOOL: calc\nARGS: {{"expression": "{i}+{i}"}}' for i in range(10)
        ])
        loop = AgentLoop(p, build_tools(["calc"]), make_cfg(tmp, max_steps=3))
        out, steps, stop = loop.run("现在几点")
        self.assertEqual(stop, "max_steps")
        self.assertEqual(len(steps), 3)
        self.assertIn("[停止]", out)

    def test_invalid_action_fed_back(self):
        tmp = Path(tempfile.mkdtemp())
        p = ScriptedProvider([
            'TOOL: 不存在\nARGS: {}',
            "FINAL: 改好了",
        ])
        loop = AgentLoop(p, build_tools(["calc"]), make_cfg(tmp))
        out, steps, stop = loop.run("随便")
        self.assertEqual(out, "改好了")
        self.assertEqual(steps[0]["type"], "invalid")
        self.assertIn("无效动作", steps[0]["observation"])
        # 第二轮 transcript 应包含错误反馈
        self.assertIn("无效动作", p.calls[1])

    def test_loop_detection(self):
        tmp = Path(tempfile.mkdtemp())
        p = ScriptedProvider(['TOOL: now\nARGS: {"format": "%Y"}'] * 10)
        loop = AgentLoop(p, build_tools(["now"]), make_cfg(tmp))
        out, steps, stop = loop.run("时间")
        self.assertEqual(stop, "loop_detected")


class ToolsTest(unittest.TestCase):
    def test_calc_and_registry_scope(self):
        tools = build_tools([])
        self.assertIn("http_get", tools)
        scoped = build_tools(["calc"])
        self.assertEqual(list(scoped.keys()), ["calc"])
        self.assertIn("= 7", scoped["calc"].func({"expression": "1+2*3"}))

    def test_read_write_scoped(self):
        tools = build_tools(["read_file", "write_file"])
        w = tools["write_file"].func({"path": "data/_t.txt", "content": "hi"})
        self.assertIn("已写入", w)
        r = tools["read_file"].func({"path": "data/_t.txt"})
        self.assertEqual(r, "hi")
        bad = tools["read_file"].func({"path": "../../etc/passwd"})
        self.assertIn("越界", bad)

    def test_run_python(self):
        tools = build_tools(["run_python"])
        out = tools["run_python"].func({"code": "print(40+2)"})
        self.assertEqual(out, "42")


if __name__ == "__main__":
    unittest.main()
