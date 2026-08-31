"""BlueDeer 修复引擎核心：Healer 类。

P2-1 拆分自 core/healer.py。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from core.healer_records import FixRecord, FixResult
from core.healer_strategies import _ERROR_STRATEGY, _RETRY_TEMPLATE, FixStrategy
from core.test_runner import TestFailure, TestRunner

logger = logging.getLogger("bluedeer.healer")


class Healer:
    """修复引擎：分析失败 → 应用修复 → 验证。

    P7 mock 模式：
    - RETRY_GENERATE：用模板代码覆盖目标文件
    - FIX_IMPORT：在文件头插入 import 语句
    - FIX_ASSERTION：标注需人工介入（不自动改断言）
    - ESCALATE：记录告警
    """

    def __init__(
        self,
        test_runner: TestRunner | None = None,
        history_path: str = "logs/healer_history.json",
    ) -> None:
        self._runner = test_runner or TestRunner()
        self._history_path = history_path
        self._history: list[FixRecord] = []
        self._load_history()

    # ============== 分析 ==============

    def analyze(
        self, failures: list[TestFailure]
    ) -> list[tuple[TestFailure, FixStrategy]]:
        """分析失败模式，匹配修复策略。

        Args:
            failures: 失败列表。

        Returns:
            [(TestFailure, FixStrategy), ...]
        """
        result: list[tuple[TestFailure, FixStrategy]] = []
        for f in failures:
            strategy = _ERROR_STRATEGY.get(f.error_type, FixStrategy.ESCALATE)
            result.append((f, strategy))
            logger.info(
                "分析失败: %s, error_type=%s → strategy=%s",
                f.test_id,
                f.error_type,
                strategy.value,
            )
        return result

    # ============== 应用修复 ==============

    def _get_fix_strategy_info(
        self, strategy: FixStrategy, target_file: str, failure: TestFailure
    ) -> tuple[Any, str]:
        if strategy == FixStrategy.RETRY_GENERATE:
            return self._apply_retry_generate(
                target_file, failure
            ), f"用模板代码覆盖 {target_file}"
        elif strategy == FixStrategy.FIX_IMPORT:
            return self._apply_fix_import(
                target_file, failure
            ), f"插入 import 语句到 {target_file}"
        elif strategy == FixStrategy.FIX_ASSERTION:
            return False, "断言失败需人工介入"
        elif strategy == FixStrategy.FIX_DEADLOCK:
            return self._apply_fix_deadlock(
                target_file, failure
            ), f"死锁修复（加超时）: {target_file}"
        elif strategy == FixStrategy.FIX_DEPENDENCY:
            return self._apply_fix_dependency(
                target_file, failure
            ), f"依赖冲突修复: {target_file}"
        elif strategy == FixStrategy.FIX_INTERFACE:
            return self._apply_fix_interface(
                target_file, failure
            ), f"接口字段兼容修复: {target_file}"
        elif strategy == FixStrategy.FIX_PATH:
            return self._apply_fix_path(
                target_file, failure
            ), f"路径兼容修复: {target_file}"
        elif strategy == FixStrategy.FIX_MEMORY_LEAK:
            return self._apply_fix_memory_leak(
                target_file, failure
            ), f"内存泄漏修复（加 cleanup）: {target_file}"
        elif strategy == FixStrategy.FIX_TIMEOUT:
            return self._apply_fix_timeout(
                target_file, failure
            ), f"超时修复（调大 timeout）: {target_file}"
        elif strategy == FixStrategy.FIX_ENCODING:
            return self._apply_fix_encoding(
                target_file, failure
            ), f"编码修复（utf-8）: {target_file}"
        elif strategy == FixStrategy.FIX_PERMISSION:
            return self._apply_fix_permission(
                target_file, failure
            ), f"权限修复: {target_file}"
        else:
            return False, "无法自动修复: ESCALATE"

    def apply_fix(
        self,
        failure: TestFailure,
        strategy: FixStrategy,
        target_file: str | None = None,
    ) -> FixResult:
        """应用单个修复策略。

        Args:
            failure: 失败记录。
            strategy: 修复策略。
            target_file: 目标文件（None 则从 failure.file 推断源文件）。

        Returns:
            FixResult。
        """
        if target_file is None:
            target_file = self._infer_source_file(failure.file)

        result = FixResult(strategy=strategy, target_file=target_file)

        try:
            applied, detail = self._get_fix_strategy_info(
                strategy, target_file, failure
            )
            result.applied = applied
            if strategy == FixStrategy.FIX_ASSERTION:
                result.detail = f"断言失败需人工介入: {failure.error_message[:80]}"
            elif strategy == FixStrategy.ESCALATE:
                result.detail = (
                    f"无法自动修复: {failure.error_type}: {failure.error_message[:80]}"
                )
                logger.warning("升级告警: %s", result.detail)
            else:
                result.detail = detail
        except Exception as e:
            logger.exception("应用修复失败")
            result.applied = False
            result.detail = f"修复异常: {e}"

        return result

    def _apply_retry_generate(self, target_file: str, failure: TestFailure) -> bool:
        """RETRY_GENERATE：用模板代码覆盖目标文件。"""
        if not target_file or not os.path.exists(target_file):
            # 文件不存在，尝试创建
            os.makedirs(os.path.dirname(target_file) or ".", exist_ok=True)

        content = _RETRY_TEMPLATE.format(
            strategy="RETRY_GENERATE",
            reason=f"{failure.error_type}: {failure.error_message[:50]}",
        )
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    def _apply_fix_import(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_IMPORT：在文件头插入 import 语句。"""
        if not target_file or not os.path.exists(target_file):
            return False

        # 从错误消息提取模块名
        # "No module named 'foo'" → foo
        # "cannot import name 'bar' from 'foo'" → from foo import bar
        msg = failure.error_message
        module_match = re.search(r"No module named ['\"](\S+)['\"]", msg)
        import_match = re.search(
            r"cannot import name ['\"](\S+)['\"] from ['\"](\S+)['\"]", msg
        )

        import_line = ""
        if import_match:
            name, module = import_match.groups()
            import_line = f"from {module} import {name}\n"
        elif module_match:
            module = module_match.group(1)
            import_line = f"import {module}\n"
        else:
            return False

        # 读取原文件，在头部插入
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()

        # 避免重复插入
        if import_line.strip() in original:
            return False

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(import_line + original)
        return True

    # ============== P7 扩容：8 种工程级修复 ==============

    def _apply_fix_deadlock(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_DEADLOCK：并发死锁修复（为 acquire 加 timeout）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()
        # 把 .acquire() 替换为 .acquire(timeout=30)
        new_content = re.sub(
            r"\.acquire\(\)",
            ".acquire(timeout=30)",
            original,
        )
        if new_content == original:
            # 无可替换的 acquire，记录告警但不算应用
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    def _apply_fix_dependency(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_DEPENDENCY：依赖冲突修复（在文件头加版本对齐注释 + try/except 兜底）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()
        # 提取冲突的模块名（简化：从错误消息取首个标识符）
        mod_match = re.search(r"module\s+['\"]?(\w+)", failure.error_message)
        mod = mod_match.group(1) if mod_match else "unknown_dep"
        # 在文件头加 try/except 兜底导入
        guard = (
            f"# P7 依赖冲突修复：{mod}\n"
            f"try:\n"
            f"    import {mod}\n"
            f"except ImportError:\n"
            f"    {mod} = None  # 依赖缺失降级\n\n"
        )
        if guard.strip() in original:
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(guard + original)
        return True

    def _apply_fix_interface(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_INTERFACE：接口字段兼容（为函数参数补默认值 None）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()
        # 把 def f(a, b) 形式的无默认参数补 =None
        new_content = re.sub(
            r"def (\w+)\(([^)]*)\)",
            lambda m: self._add_defaults(m.group(1), m.group(2)),
            original,
        )
        if new_content == original:
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    @staticmethod
    def _add_defaults(fname: str, params: str) -> str:
        """为无默认值的参数补 =None（保持 self/cls 不变）。"""
        if not params.strip():
            return f"def {fname}({params})"
        parts = [p.strip() for p in params.split(",")]
        new_parts = []
        for p in parts:
            if p in ("self", "cls", "*", "**") or "=" in p or p.startswith("*"):
                new_parts.append(p)
            else:
                new_parts.append(f"{p}=None")
        return f"def {fname}({', '.join(new_parts)})"

    def _apply_fix_path(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_PATH：路径兼容修复（把反斜杠路径转为正斜杠 + 加存在性检查）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()
        # Windows 反斜杠 → 正斜杠
        new_content = original.replace("\\", "/")
        if new_content == original:
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    def _apply_fix_memory_leak(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_MEMORY_LEAK：内存泄漏修复（在文件尾加 cleanup 注释 + gc.collect 提示）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()
        cleanup = (
            "\n\n# P7 内存泄漏修复：显式释放\n"
            "def _cleanup_resources():\n"
            "    import gc\n"
            "    gc.collect()\n"
        )
        if "_cleanup_resources" in original:
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(original + cleanup)
        return True

    def _apply_fix_timeout(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_TIMEOUT：超时修复（把 timeout=N 数字调大 3 倍）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()

        def _scale(m: re.Match) -> str:
            n = int(m.group(1))
            return f"timeout={n * 3}"

        new_content = re.sub(r"timeout=(\d+)", _scale, original)
        if new_content == original:
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    def _apply_fix_encoding(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_ENCODING：编码修复（在文件头加 # -*- coding: utf-8 -*- + 替换 open 为 utf-8）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        with open(target_file, "r", encoding="utf-8") as f:
            original = f.read()
        new_content = original
        # 补编码声明
        if "# -*- coding: utf-8 -*-" not in new_content.split("\n")[0]:
            new_content = "# -*- coding: utf-8 -*-\n" + new_content
        # open() 补 encoding="utf-8"
        new_content = re.sub(
            r"open\(([^)]+)\)(?!\s*#.*encoding)",
            lambda m: (
                m.group(0)
                if "encoding" in m.group(0)
                else f"open({m.group(1)}, encoding='utf-8')"
            ),
            new_content,
        )
        if new_content == original:
            return False
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    def _apply_fix_permission(self, target_file: str, failure: TestFailure) -> bool:
        """FIX_PERMISSION：权限修复（chmod 0644）。"""
        if not target_file or not os.path.exists(target_file):
            return False
        try:
            os.chmod(target_file, 0o644)
            return True
        except OSError as e:
            logger.warning("权限修复失败: %s", e)
            return False

    def _infer_source_file(self, test_file: str) -> str:
        """从测试文件路径推断源文件路径。

        P7 简化：直接返回测试文件本身（修复场景多为覆盖测试目标文件）。
        """
        return test_file

    # ============== 验证 ==============

    def verify(self, test_path: str) -> bool:
        """重新跑测试验证修复。

        Returns:
            True 表示全通过。
        """
        result = self._runner.run(test_path)
        return result.passed

    # ============== 完整修复闭环 ==============

    def _heal_initial_test(self, test_path: str) -> tuple[Any, dict[str, Any] | None]:
        initial = self._runner.run(test_path)
        if initial.passed:
            return initial, {
                "initial_passed": True,
                "failures_count": 0,
                "fixes_applied": 0,
                "final_passed": True,
                "fixes": [],
            }
        return initial, None

    def _heal_analyze_failures(self, test_path: str, initial: Any) -> list:
        failures = initial.failures
        if not failures and not initial.passed:
            failures = [
                TestFailure(
                    test_id=f"{test_path}::(collection)",
                    file=test_path,
                    test_name="(collection)",
                    error_type="SyntaxError",
                    error_message="collection error (likely syntax error)",
                )
            ]
            logger.info("测试失败但无具体 failures，按收集错误处理")
        return self.analyze(failures)

    def _heal_apply_fixes(
        self, analyzed: list, target_file: str | None
    ) -> tuple[list[FixResult], list[FixRecord]]:
        fixes: list[FixResult] = []
        records: list[FixRecord] = []
        for failure, strategy in analyzed:
            fix = self.apply_fix(failure, strategy, target_file)
            fixes.append(fix)
            records.append(
                FixRecord(
                    timestamp=time.time(),
                    test_id=failure.test_id,
                    strategy=strategy.value,
                    success=False,
                    target_file=fix.target_file,
                    detail=fix.detail,
                )
            )
        return fixes, records

    def _heal_verify_and_update(
        self, test_path: str, fixes: list[FixResult], records: list[FixRecord]
    ) -> bool:
        final_passed = self.verify(test_path)
        for i, fix in enumerate(fixes):
            if i < len(records):
                records[-len(fixes) + i].success = final_passed
        self._history.extend(records)
        return final_passed

    def heal(
        self,
        test_path: str,
        target_file: str | None = None,
    ) -> dict[str, Any]:
        """完整修复闭环：跑测试 → 分析 → 修复 → 验证。

        Args:
            test_path: 测试路径。
            target_file: 修复目标文件（None 则自动推断）。

        Returns:
             {
                 "initial_passed": bool,
                 "failures_count": int,
                 "fixes_applied": int,
                 "final_passed": bool,
                 "fixes": [FixResult.to_dict()],
             }
        """
        initial, early = self._heal_initial_test(test_path)
        if early is not None:
            return early
        analyzed = self._heal_analyze_failures(test_path, initial)
        fixes, records = self._heal_apply_fixes(analyzed, target_file)
        final_passed = self._heal_verify_and_update(test_path, fixes, records)
        self._save_history()
        return {
            "initial_passed": False,
            "failures_count": len(initial.failures),
            "fixes_applied": sum(1 for f in fixes if f.applied),
            "final_passed": final_passed,
            "fixes": [f.to_dict() for f in fixes],
            "initial_result": initial.to_dict(),
        }

    # ============== 历史记录 ==============

    def get_history(self) -> list[FixRecord]:
        """获取修复历史。"""
        return list(self._history)

    def clear_history(self) -> None:
        """清空历史。"""
        self._history.clear()
        self._save_history()

    def _load_history(self) -> None:
        """加载历史。"""
        if not os.path.exists(self._history_path):
            return
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._history = [FixRecord(**item) for item in data]
        except (OSError, json.JSONDecodeError, TypeError) as e:
            logger.warning("加载修复历史失败: %s", e)
            self._history = []

    def _save_history(self) -> None:
        """保存历史。"""
        os.makedirs(os.path.dirname(self._history_path) or ".", exist_ok=True)
        try:
            with open(self._history_path, "w", encoding="utf-8") as f:
                json.dump(
                    [r.to_dict() for r in self._history],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError as e:
            logger.warning("保存修复历史失败: %s", e)
