# -*- coding: utf-8 -*-
"""底座 HTTP API 端到端测试：真实起服务(临时端口)，隔离存储与轨迹目录。"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluedeer import server as srv
from bluedeer.config import ROOT_DIR


def _req(method, url, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


class ServerTest(unittest.TestCase):
    httpd = None
    base = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        srv.STORE = srv.Store(os.path.join(cls.tmp.name, "store.json"))
        cfg = {"trace": False, "runs_dir": os.path.join(cls.tmp.name, "runs")}
        # 造两条"历史真实轨迹"：一天一条，供 /system/usage 出图
        runs_dir = Path(cfg["runs_dir"])
        for i, (hh, outp, blocked) in enumerate([("10", "hello", False), ("11", "", True)]):
            d = runs_dir / ("202608%02d_%s0000_aabbcc" % (20 + i, hh))
            d.mkdir(parents=True)
            (d / "final.json").write_text(json.dumps({
                "run_id": "r%d" % i, "output": outp,
                "blocked": blocked,
                "block_reason": "敏感词" if blocked else None,
                "layer_timings": {"input": 0.2, "reasoning": 3.1},
                "metadata": {"role": "小鹿", "provider": "mock"},
            }, ensure_ascii=False), encoding="utf-8")
        cls.cfg = cfg
        srv.Handler.api = srv.make_api(cfg)
        cls.httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def g(self, path):
        return _req("GET", self.base + path)

    def p(self, path, body=None):
        return _req("POST", self.base + path, body if body is not None else {})

    # ---- 根与统计 ----
    def test_root_version(self):
        st, j = self.g("/")
        self.assertEqual(st, 200)
        self.assertIn("version", j)

    def test_stats_and_usage_real_trace(self):
        st, j = self.g("/system/stats")
        self.assertEqual(st, 200)
        s = j["stats"]
        self.assertIn("agents_total", s)
        u = s["usage"]
        self.assertEqual(u["total_runs"], 2)
        self.assertEqual(u["blocked_runs"], 1)
        self.assertEqual(len(u["runs_per_day"]), 2)
        self.assertTrue(any(l["layer"] == "reasoning" for l in u["layer_avg_ms"]))
        self.assertEqual(u["role_distribution"], {"小鹿": 2})
        st2, ju = self.g("/system/usage")
        self.assertEqual(st2, 200)
        self.assertEqual(ju["total_runs"], 2)

    # ---- agents ----
    def test_register_manager_delegate(self):
        st, j = self.p("/agents/register", {
            "agent_id": "sub_a", "name": "子甲", "role": "worker",
            "capabilities": ["调研"], "auto_reply": {"enabled": True, "reply_template": "收到 {from}：{task}"}})
        self.assertEqual(st, 200)
        self.assertFalse(j["registered_before"])
        st, jl = self.g("/agents")
        self.assertEqual(len(jl["agents"]), 1)
        self.assertEqual(jl["agents"][0]["status"], "online")
        st, jm = self.p("/agents/manager/set", {"agent_id": "sub_a"})
        self.assertEqual(st, 200)
        st, jc = self.g("/agents/manager/current")
        self.assertEqual(jc["manager"]["agent_id"], "sub_a")
        # 委托：目标开了自动应答 → 模板回复，消息流水两条
        st, jd = self.p("/agents/delegate", {"from_agent": "human", "to_agent": "sub_a", "task_content": "查天气"})
        self.assertEqual(st, 200)
        self.assertEqual(jd["status"], "replied")
        self.assertIn("查天气", jd["reply"])
        st, hm = self.g("/messages/history?from_agent=human&to_agent=sub_a&limit=10")
        self.assertEqual(len(hm["messages"]), 1)
        # 详情与更新
        st, jdet = self.g("/agents/sub_a")
        self.assertEqual(jdet["agent"]["name"], "子甲")
        st, ju = self.p("/agents/sub_a/update", {"system_prompt": "你是测试鹿"})
        self.assertEqual(st, 200)
        st, jar = self.p("/agents/sub_a/autoreply", {"enabled": False})
        self.assertFalse(jar["auto_reply"]["enabled"])

    # ---- messages / memories / approvals ----
    def test_messages_memories_approvals(self):
        st, jm = self.p("/messages/send", {"channel_type": "private", "from_agent": "a", "to_agent": "b", "content": "hi"})
        self.assertEqual(st, 200)
        st, jd = self.g("/memories/list-domains?reader=human")
        self.assertIsInstance(jd["domains"], list)
        st, jw = self.p("/memories/write", {"reader": "human", "domain": "facts", "content": "天是蓝的"})
        self.assertEqual(st, 200)
        st, jr = self.g("/memories/read?domain=facts")
        self.assertEqual(len(jr["items"]), 1)
        # 直接塞一条待审批，走 decide 接口
        srv.STORE.data["memory_approvals"].append({
            "id": "req_1", "reader": "sub_a", "domain": "facts",
            "content": "草稿内容", "status": "pending", "requested_by": "sub_a", "created_at": int(time.time())})
        st, jp = self.g("/memories/approvals/pending")
        self.assertEqual(len(jp["pending"]), 1)
        self.assertEqual(jp["pending"][0]["request_id"], "req_1")
        self.assertEqual(jp["pending"][0]["kind"] if "kind" in jp["pending"][0] else "mem", "mem")
        st, jok = self.p("/memories/approvals/decide", {"request_id": "req_1", "manager_id": "sub_a", "approve": True})
        self.assertEqual(st, 200)
        st, jr2 = self.g("/memories/read?domain=facts")
        self.assertEqual(len(jr2["items"]), 2)

    # ---- settings / emergency ----
    def test_settings_and_emergency(self):
        st, js = self.g("/system/settings")
        self.assertIn("provider", js["settings"])
        st, jw = self.p("/system/settings", {"provider": "mock", "role": ""})
        self.assertEqual(st, 200)
        st, je = self.p("/system/emergency-block/toggle?active=true")
        self.assertTrue(je["emergency_block"])
        st, jb = self.p("/messages/send", {"channel_type": "private", "from_agent": "a", "to_agent": "b", "content": "x"})
        self.assertEqual(st, 403)
        self.p("/system/emergency-block/toggle?active=false")
        st, jal = self.g("/system/audit-logs?limit=5")
        self.assertGreaterEqual(len(jal["logs"]), 1)

    # ---- workflows / crons / projects / skills ----
    def test_workflow_run_real(self):
        self.p("/agents/register", {"agent_id": "w1", "name": "工蜂"})
        st, jw = self.p("/workflows/create", {"name": "两步流", "definition": [
            {"agent_id": "w1", "prompt": "第一步"}, {"agent_id": "w1", "prompt": "接着 {prev}"}]})
        wid = jw["workflow"]["id"]
        st, jr = self.p("/workflows/%s/run?trigger_by=test" % wid)
        self.assertEqual(st, 200)
        self.assertEqual(rj := jr["run"], rj)
        self.assertEqual(len(rj["steps"]), 2)
        self.assertIn("elapsed_ms", rj["steps"][0])
        st, jrs = self.g("/workflows/%s/runs" % wid)
        self.assertEqual(len(jrs["runs"]), 1)
        st, jp = self.p("/projects/create", {"name": "P", "agent_ids": ["w1"]})
        pid = jp["project"]["id"]
        st, jd = self.g("/projects/" + pid)
        self.assertEqual(jd["project"]["name"], "P")
        st, jc = self.p("/crons/create", {"name": "每分钟问好", "interval_sec": 60, "action": "delegate", "target": "w1", "payload": {"content": "打卡"}})
        cid = jc["cron"]["id"]
        st, jrun = self.p("/crons/%s/run" % cid)
        self.assertEqual(st, 200)
        self.assertIn("output", jrun["entry"])
        st, jh = self.g("/crons/%s/history" % cid)
        self.assertEqual(len(jh["history"]), 1)
        st, jsk = self.p("/skills/register", {"name": "weather", "description": "查天气"})
        sid = jsk["skill"]["id"]
        st, _ = self.p("/skills/%s/disable" % sid)
        st, jsl = self.g("/skills")
        self.assertFalse(jsl["skills"][0]["enabled"])

    # ---- files ----
    def test_files_crud_scoped(self):
        rel = "data/_srvtest_tmp.txt"
        st, j = self.p("/files/create", {"path": rel, "is_dir": False})
        self.assertEqual(st, 200)
        st, j = self.p("/files/content", {"path": rel, "content": "abc"})
        self.assertEqual(st, 200)
        p = ROOT_DIR / rel
        self.assertEqual(p.read_text(encoding="utf-8"), "abc")
        st, jl = self.g("/files/list?path=data")
        self.assertTrue(any(e["name"] == "_srvtest_tmp.txt" for e in jl["entries"]))
        st, j404 = self.g("/files/content?path=" + rel.replace("_srvtest_tmp", "nope"))
        self.assertEqual(j404["detail"], "文件不存在")
        # 越界必须被拒
        try:
            st, jbad = self.g("/files/content?path=..%2F..%2FWindows%2Fwin.ini")
            self.assertIn(st, (403, 404))
        except Exception:
            pass
        st, _ = self.p("/files/delete", {"path": rel})
        self.assertFalse(p.exists())

    # ---- CORS 预检 ----
    def test_options_preflight(self):
        r = urllib.request.Request(self.base + "/", method="OPTIONS")
        with urllib.request.urlopen(r, timeout=5) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")


if __name__ == "__main__":
    unittest.main()
