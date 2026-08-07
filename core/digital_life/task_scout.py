"""commit 38：主动任务发现。

零基础读者可以这样理解：
- 智能体不再被动等命令，而是定期"巡视"项目状态
- 发现值得改进的地方就主动提建议（如"某模块改了很多但没测试"）
- 监工可以采纳/推迟/拒绝这些建议
- 连续被拒绝 5 次的物种会降低建议频率

存储路径：data/task_suggestions.json
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any
# ruff: noqa: S110, S112

# ----------------------------------------------------------------------
# 存储路径与常量
# ----------------------------------------------------------------------

_SUGGESTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "task_suggestions.json",
)

# 建议状态
SUGG_PENDING = "pending"  # 待处理
SUGG_ADOPTED = "adopted"  # 已采纳
SUGG_DEFERRED = "deferred"  # 已推迟
SUGG_REJECTED = "rejected"  # 已拒绝
SUGG_EXPIRED = "expired"  # 已过期（48 小时未处理）

# 物种中文名
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

# 任务类型→推荐物种
_TASK_TYPE_TO_SPECIES: dict[str, str] = {
    "代码生成-算法实现": "squirrel",
    "代码生成-安全相关": "squirrel",
    "代码生成-业务逻辑": "squirrel",
    "UI-界面设计": "butterfly",
    "UI-交互体验": "butterfly",
    "测试-单元测试": "fox",
    "测试-模糊测试": "fox",
    "测试-覆盖率": "fox",
    "安全-漏洞扫描": "hedgehog",
    "安全-审计": "hedgehog",
    "运维-部署": "beaver",
    "运维-存储": "beaver",
    "检索-向量": "raven",
    "检索-倒排": "raven",
    "统计-数据分析": "hare",
    "网络-接口调试": "badger",
    "监控-告警": "lark",
    "调度-拓扑规划": "kite",
}


# ----------------------------------------------------------------------
# TaskScout 单例
# ----------------------------------------------------------------------


class TaskScout:
    """主动任务发现（单例）。

    零基础理解：这是公司的"巡检员"，每小时扫一遍项目状态，
    发现值得改的地方就主动提建议给监工。
    """

    _instance: TaskScout | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._suggestions: list[dict] = []
        self._loaded = False
        self._load()
        self._biosphere: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interval: float = 3600.0  # 默认 1 小时
        self._reject_counts: dict[str, int] = {}  # {species: 连续拒绝次数}

    @classmethod
    def get_instance(cls) -> TaskScout:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_biosphere(self, biosphere: Any) -> None:
        self._biosphere = biosphere

    # ---------------- 持久化 ----------------

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            try:
                if os.path.exists(_SUGGESTION_PATH):
                    with open(_SUGGESTION_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._suggestions = data.get("suggestions", []) or []
                    self._reject_counts = data.get("reject_counts", {}) or {}
            except (json.JSONDecodeError, OSError):
                self._suggestions = []
                self._reject_counts = {}
            self._loaded = True

    def _save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(_SUGGESTION_PATH), exist_ok=True)
                with open(_SUGGESTION_PATH, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "suggestions": self._suggestions,
                            "reject_counts": self._reject_counts,
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except OSError:
                pass

    # ---------------- 生命周期 ----------------

    def start(self, interval: float = 3600.0) -> None:
        """启动后台扫描线程。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._interval = max(60.0, float(interval))
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="task-scout",
            )
            self._thread.start()

    def stop(self) -> None:
        """停止扫描线程。"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run_loop(self) -> None:
        """扫描循环：每 interval 秒扫一次。"""
        while not self._stop_event.is_set():
            try:
                self.scan_once()
            except Exception:
                pass
            # 等待 interval 或 stop
            self._stop_event.wait(self._interval)

    # ---------------- 扫描 ----------------

    def scan_once(self) -> dict:
        """执行一次完整扫描。返回扫描结果摘要。

        Returns:
            {"findings": list[dict], "suggestions_generated": int, "ts": float}
        """
        findings: list[dict] = []
        # 6 种扫描
        findings.extend(self._scan_file_changes())
        findings.extend(self._scan_test_coverage())
        findings.extend(self._scan_security_logs())
        findings.extend(self._scan_tool_failures())
        findings.extend(self._scan_experience_stats())
        findings.extend(self._scan_workforce())

        # 生成建议
        suggestions = self._generate_suggestions(findings)
        with self._lock:
            for s in suggestions:
                self._suggestions.append(s)
            # 过期处理
            self._expire_old()
            # 上限 200 条
            if len(self._suggestions) > 200:
                self._suggestions = self._suggestions[-200:]
            self._save()

        return {
            "findings": findings,
            "suggestions_generated": len(suggestions),
            "ts": time.time(),
        }

    def _scan_file_changes(self) -> list[dict]:
        """扫描项目 .py 文件 7 天内修改情况。"""
        findings: list[dict] = []
        try:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            now = time.time()
            week_ago = now - 7 * 86400
            hot_files: list[str] = []
            for root, dirs, files in os.walk(project_root):
                # 跳过 .git / __pycache__ / data
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in (".git", "__pycache__", "data", "node_modules", ".venv")
                ]
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        mtime = os.path.getmtime(fpath)
                        if mtime > week_ago:
                            hot_files.append(os.path.relpath(fpath, project_root))
                    except OSError:
                        continue
            if len(hot_files) > 10:
                findings.append(
                    {
                        "category": "file_changes",
                        "severity": "info",
                        "data": {
                            "hot_files_count": len(hot_files),
                            "sample": hot_files[:5],
                        },
                        "message": f"近 7 天有 {len(hot_files)} 个 .py 文件被修改",
                    }
                )
        except Exception:
            pass
        return findings

    def _scan_test_coverage(self) -> list[dict]:
        """扫描 tests/ 目录 vs core/ 模块比例。"""
        findings: list[dict] = []
        try:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            core_dir = os.path.join(project_root, "core")
            tests_dir = os.path.join(project_root, "tests")
            core_count = 0
            tests_count = 0
            if os.path.isdir(core_dir):
                for root, dirs, files in os.walk(core_dir):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for f in files:
                        if f.endswith(".py"):
                            core_count += 1
            if os.path.isdir(tests_dir):
                for root, dirs, files in os.walk(tests_dir):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for f in files:
                        if f.endswith(".py"):
                            tests_count += 1
            if core_count > 0:
                ratio = tests_count / core_count
                if ratio < 0.5:
                    findings.append(
                        {
                            "category": "test_coverage",
                            "severity": "warning",
                            "data": {
                                "core_modules": core_count,
                                "test_files": tests_count,
                                "ratio": round(ratio, 2),
                            },
                            "message": f"测试覆盖率不足（{tests_count} 测试/{core_count} 模块，比例 {ratio:.2f}）",
                        }
                    )
        except Exception:
            pass
        return findings

    def _scan_security_logs(self) -> list[dict]:
        """扫描 logs/ 目录异常条目。"""
        findings: list[dict] = []
        try:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            logs_dir = os.path.join(project_root, "logs")
            if not os.path.isdir(logs_dir):
                return findings
            error_count = 0
            warn_count = 0
            for fname in os.listdir(logs_dir):
                fpath = os.path.join(logs_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "ERROR" in line or "CRITICAL" in line:
                                error_count += 1
                            elif "WARN" in line:
                                warn_count += 1
                except OSError:
                    continue
            if error_count > 0 or warn_count > 20:
                findings.append(
                    {
                        "category": "security_logs",
                        "severity": "warning" if error_count > 0 else "info",
                        "data": {"errors": error_count, "warnings": warn_count},
                        "message": f"日志中发现 {error_count} 条错误、{warn_count} 条警告",
                    }
                )
        except Exception:
            pass
        return findings

    def _scan_tool_failures(self) -> list[dict]:
        """扫描 ToolExecutor 历史失败。"""
        findings: list[dict] = []
        try:
            from core.digital_life.tool_executor import get_tool_executor

            history = get_tool_executor().list_history(limit=100)
            fail_count = sum(1 for h in history if not h.get("ok", True))
            if fail_count > 3:
                findings.append(
                    {
                        "category": "tool_failures",
                        "severity": "warning",
                        "data": {"failures": fail_count, "total": len(history)},
                        "message": f"近 100 次工具调用中有 {fail_count} 次失败",
                    }
                )
        except Exception:
            pass
        return findings

    def _scan_experience_stats(self) -> list[dict]:
        """扫描经验库覆盖缺口。"""
        findings: list[dict] = []
        try:
            from core.digital_life.experience_library import (
                TASK_TYPE_KEYWORDS,
                get_experience_library,
            )

            stats = get_experience_library().stats()
            covered_types = set(stats.get("by_type", {}).keys())
            all_types = set(TASK_TYPE_KEYWORDS.keys())
            missing = all_types - covered_types
            if len(missing) > 5:
                findings.append(
                    {
                        "category": "experience_gap",
                        "severity": "info",
                        "data": {
                            "missing_types": list(missing)[:10],
                            "missing_count": len(missing),
                        },
                        "message": f"经验库覆盖不足（{len(missing)} 类任务暂无经验）",
                    }
                )
        except Exception:
            pass
        return findings

    def _scan_workforce(self) -> list[dict]:
        """扫描员工状态（能量/生病/待办）。"""
        findings: list[dict] = []
        if self._biosphere is None:
            return findings
        try:
            employees = getattr(self._biosphere, "employees", []) or []
            alive = [e for e in employees if getattr(e, "_alive", False)]
            if not alive:
                return findings
            low_energy = []
            sick = []
            overloaded = []
            for e in alive:
                energy = float(getattr(e, "energy", 50) or 50)
                if energy < 30:
                    low_energy.append(getattr(e, "species", "?"))
                if getattr(e, "illness", None) is not None:
                    sick.append(getattr(e, "species", "?"))
                pending = len(getattr(e, "_pipeline_task_inbox", []) or [])
                if pending >= 3:
                    overloaded.append(getattr(e, "species", "?"))
            if sick:
                findings.append(
                    {
                        "category": "workforce",
                        "severity": "warning",
                        "data": {"sick_species": sick},
                        "message": f"{len(sick)} 个智能体生病，建议监工关注",
                    }
                )
            if low_energy:
                findings.append(
                    {
                        "category": "workforce",
                        "severity": "info",
                        "data": {"low_energy_species": low_energy},
                        "message": f"{len(low_energy)} 个智能体能量偏低",
                    }
                )
        except Exception:
            pass
        return findings

    # ---------------- 建议生成 ----------------

    def _generate_suggestions(self, findings: list[dict]) -> list[dict]:
        """根据扫描结果生成建议。"""
        suggestions: list[dict] = []
        now = time.time()
        for f in findings:
            category = f.get("category", "")
            severity = f.get("severity", "info")
            message = f.get("message", "")
            if not message:
                continue
            # 根据 category 推荐物种
            species_hint = "deer"
            if category == "test_coverage":
                species_hint = "fox"
            elif category == "security_logs":
                species_hint = "hedgehog"
            elif category == "tool_failures":
                species_hint = "fox"
            elif category == "experience_gap" or category == "workforce":
                species_hint = "deer"
            elif category == "file_changes":
                species_hint = "squirrel"

            # 跳过连续拒绝 5 次的物种
            if self._reject_counts.get(species_hint, 0) >= 5:
                continue

            sugg = {
                "id": "sugg-" + uuid.uuid4().hex[:8],
                "title": message[:80],
                "reason": message,
                "category": category,
                "severity": severity,
                "species_hint": species_hint,
                "workload": "中" if severity == "warning" else "轻",
                "status": SUGG_PENDING,
                "created_ts": now,
                "expire_ts": now + 48 * 3600,  # 48 小时过期
                "decided_ts": 0,
                "decide_reason": "",
            }
            suggestions.append(sugg)
        return suggestions

    def _expire_old(self) -> None:
        """把过期的 pending 建议标记为 expired。"""
        now = time.time()
        for s in self._suggestions:
            if s.get("status") == SUGG_PENDING and s.get("expire_ts", 0) < now:
                s["status"] = SUGG_EXPIRED
                s["decided_ts"] = now

    # ---------------- 监工操作 ----------------

    def adopt(self, sugg_id: str) -> dict:
        """采纳建议：自动建任务并分配给推荐物种。

        Returns:
            {"ok": bool, "task_id": str, "note": str}
        """
        with self._lock:
            sugg = None
            for s in self._suggestions:
                if s.get("id") == sugg_id:
                    sugg = s
                    break
            if sugg is None:
                return {"ok": False, "error": "建议不存在"}
            if sugg.get("status") != SUGG_PENDING:
                return {
                    "ok": False,
                    "error": f"建议状态非 pending（{sugg.get('status')}）",
                }
            sugg["status"] = SUGG_ADOPTED
            sugg["decided_ts"] = time.time()
            self._save()

        # 重置该物种的拒绝计数
        species = sugg.get("species_hint", "")
        if species:
            with self._lock:
                self._reject_counts[species] = 0
                self._save()

        # 自动建任务（如果 biosphere 可用）
        task_id = ""
        note = ""
        if self._biosphere is not None:
            try:
                from core.digital_life.task_pipeline import get_pipeline_engine

                pe = get_pipeline_engine()
                if pe._biosphere_ref is None and self._biosphere is not None:
                    pe.set_biosphere(self._biosphere)
                result = pe.submit(
                    sugg.get("title", ""), name=sugg.get("title", "")[:30]
                )
                if result.get("ok"):
                    task_id = result.get("pipeline_id", "")
                    note = f"已自动派给 {species}，流水线 ID: {task_id[:8]}"
                else:
                    note = f"采纳但派活失败：{result.get('error', '')[:60]}"
            except Exception as e:
                note = f"采纳但派活异常：{str(e)[:60]}"
        else:
            note = "采纳成功（无 biosphere，未自动派活）"

        return {"ok": True, "task_id": task_id, "note": note}

    def defer(self, sugg_id: str, hours: float = 24.0) -> dict:
        """推迟建议（重新设置过期时间）。"""
        with self._lock:
            for s in self._suggestions:
                if s.get("id") == sugg_id:
                    if s.get("status") != SUGG_PENDING:
                        return {
                            "ok": False,
                            "error": f"建议状态非 pending（{s.get('status')}）",
                        }
                    s["status"] = SUGG_DEFERRED
                    s["decided_ts"] = time.time()
                    s["expire_ts"] = time.time() + hours * 3600
                    # 推迟到期后重新变 pending
                    s["deferred_until"] = s["expire_ts"]
                    s["status"] = SUGG_PENDING  # 重新设为 pending 等到期再处理
                    s["expire_ts"] = time.time() + hours * 3600
                    self._save()
                    return {"ok": True, "note": f"已推迟 {hours} 小时"}
            return {"ok": False, "error": "建议不存在"}

    def reject(self, sugg_id: str, reason: str = "") -> dict:
        """拒绝建议（记录原因 + 该物种拒绝计数 +1）。"""
        with self._lock:
            for s in self._suggestions:
                if s.get("id") == sugg_id:
                    if s.get("status") != SUGG_PENDING:
                        return {
                            "ok": False,
                            "error": f"建议状态非 pending（{s.get('status')}）",
                        }
                    s["status"] = SUGG_REJECTED
                    s["decided_ts"] = time.time()
                    s["decide_reason"] = (reason or "")[:200]
                    species = s.get("species_hint", "")
                    if species:
                        self._reject_counts[species] = (
                            self._reject_counts.get(species, 0) + 1
                        )
                    self._save()
                    return {
                        "ok": True,
                        "note": f"已拒绝；{species} 连续拒绝 "
                        f"{self._reject_counts.get(species, 0)} 次",
                    }
            return {"ok": False, "error": "建议不存在"}

    # ---------------- 查询 ----------------

    def list_suggestions(self, status: str = "", limit: int = 50) -> list[dict]:
        """列出建议（按时间倒序）。"""
        with self._lock:
            results = []
            for s in self._suggestions:
                if status and s.get("status") != status:
                    continue
                results.append(dict(s))
            results.sort(key=lambda x: x.get("created_ts", 0), reverse=True)
            return results[:limit]

    def stats(self) -> dict:
        """采纳率统计。"""
        with self._lock:
            total = len(self._suggestions)
            adopted = sum(
                1 for s in self._suggestions if s.get("status") == SUGG_ADOPTED
            )
            rejected = sum(
                1 for s in self._suggestions if s.get("status") == SUGG_REJECTED
            )
            pending = sum(
                1 for s in self._suggestions if s.get("status") == SUGG_PENDING
            )
            deferred = sum(
                1 for s in self._suggestions if s.get("status") == SUGG_DEFERRED
            )
            expired = sum(
                1 for s in self._suggestions if s.get("status") == SUGG_EXPIRED
            )
            decided = adopted + rejected
            adopt_rate = (adopted / decided) if decided > 0 else 0.0
            return {
                "total": total,
                "pending": pending,
                "adopted": adopted,
                "rejected": rejected,
                "deferred": deferred,
                "expired": expired,
                "adopt_rate": round(adopt_rate, 3),
                "reject_counts": dict(self._reject_counts),
            }


# ----------------------------------------------------------------------
# 模块级便捷 API
# ----------------------------------------------------------------------


def get_task_scout() -> TaskScout:
    return TaskScout.get_instance()
