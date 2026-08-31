"""追踪与角色卡测试：验证逐层快照落盘、final.json、角色加载。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bluedeer.agent import BlueDeerAgent  # noqa: E402
from bluedeer.roles import list_roles, load_role, resolve_system_prompt  # noqa: E402


def base_cfg(tmp: Path) -> dict:
    return {
        "provider": "mock",
        "trace": True,
        "runs_dir": str(tmp / "runs"),
        "role": "",
        "roles_dir": "",
        "system_prompt": "",
    }


class TraceTest(unittest.TestCase):
    def test_run_writes_snapshots_and_final(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = BlueDeerAgent(base_cfg(tmp))
            out = agent.run("你好")
            self.assertTrue(out.startswith("[Mock回复]"))
            run_dirs = list((tmp / "runs").iterdir())
            self.assertEqual(len(run_dirs), 1)
            files = sorted(p.name for p in run_dirs[0].glob("*.json"))
            self.assertIn("00_input.json", files)
            self.assertIn("12_monitoring.json", files)
            self.assertIn("final.json", files)
            self.assertEqual(len(files), 14)

    def test_trace_off_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = base_cfg(tmp)
            cfg["trace"] = False
            agent = BlueDeerAgent(cfg)
            agent.run("你好")
            self.assertFalse((tmp / "runs").exists())


class RolesTest(unittest.TestCase):
    def test_load_role_from_md(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "小鹿.md").write_text("# 小鹿\n你是忧郁鹿。", encoding="utf-8")
            self.assertEqual(list_roles(d), ["小鹿"])
            role = load_role(d, "小鹿")
            self.assertIsNotNone(role)
            self.assertEqual(role.name, "小鹿")
            self.assertIn("忧郁鹿", role.system_prompt)

    def test_resolve_priority(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "a.md").write_text("# A\nROLE_A", encoding="utf-8")
            cfg = {"role": "a", "roles_dir": str(d), "system_prompt": "INLINE"}
            self.assertIn("ROLE_A", resolve_system_prompt(cfg))
            cfg2 = {"role": "", "roles_dir": str(d), "system_prompt": "INLINE"}
            self.assertEqual(resolve_system_prompt(cfg2), "INLINE")
            cfg3 = {"role": "missing", "roles_dir": str(d), "system_prompt": ""}
            self.assertIsNone(resolve_system_prompt(cfg3))


if __name__ == "__main__":
    unittest.main()
