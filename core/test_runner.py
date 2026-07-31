"""BlueDeer 测试运行器：subprocess 调 pytest + 解析输出。

纯标准库，不把 pytest 当库依赖，仅通过 subprocess 调用并解析文本输出。

P7 扩容（A 级）：
- TestType 枚举：UNIT / INTEGRATION / SECURITY / ART_SPEC / COMMIT_LINT 5 类测试覆盖
- TestRunner.run 支持指定 test_type，按类型选择 pytest 标记/参数
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("bluedeer.test_runner")

# pytest 超时（秒）
_DEFAULT_TIMEOUT = 60


class TestType(Enum):
    """P7 扩容：测试类型（5 类覆盖）。

    - UNIT：单元测试（原行为，仅函数级语法/逻辑测试）
    - INTEGRATION：集成测试（跨模块组合验证）
    - SECURITY：安全扫描测试（漏洞规则校验）
    - ART_SPEC：美术素材规范校验（精灵尺寸/色板/命名）
    - COMMIT_LINT：仓库提交规范校验（commit message 格式）
    """
    UNIT = "unit"
    INTEGRATION = "integration"
    SECURITY = "security"
    ART_SPEC = "art_spec"
    COMMIT_LINT = "commit_lint"


# 测试类型 → pytest 标记/参数（P7 扩容）
_TEST_TYPE_ARGS: dict[TestType, list[str]] = {
    TestType.UNIT: [],  # 默认行为，无额外参数
    TestType.INTEGRATION: ["-m", "integration"],
    TestType.SECURITY: ["-m", "security"],
    TestType.ART_SPEC: ["-m", "art_spec"],
    TestType.COMMIT_LINT: ["-m", "commit_lint"],
}


@dataclass
class TestFailure:
    """单个测试失败记录。"""
    # 抑制 pytest 收集警告（类名以 Test 开头）
    __test__ = False

    test_id: str = ""          # 完整 ID：tests/test_x.py::test_name
    file: str = ""             # 测试文件
    test_name: str = ""        # 测试函数名
    error_type: str = ""       # 错误类型（AssertionError / SyntaxError 等）
    error_message: str = ""    # 错误消息

    def to_dict(self) -> dict[str, str]:
        return {
            "test_id": self.test_id,
            "file": self.file,
            "test_name": self.test_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass
class TestRunResult:
    """测试运行结果。"""
    # 抑制 pytest 收集警告
    __test__ = False

    passed: bool = False
    total: int = 0             # 总测试数
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0       # 收集错误数
    failures: list[TestFailure] = field(default_factory=list)
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": self.total,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "error_count": self.error_count,
            "failures": [f.to_dict() for f in self.failures],
            "duration_ms": self.duration_ms,
            "returncode": self.returncode,
        }


# pytest -q --tb=short 失败/错误行正则
# FAILED 格式：FAILED tests/test_x.py::test_name - ErrorType: message
#              FAILED tests/test_x.py::test_name - assert expr
# ERROR 格式： ERROR tests/test_x.py - ErrorType: message （收集阶段错误，无 ::test_name）
_FAILED_PATTERN = re.compile(
    r"(?:FAILED|ERROR)\s+(\S+?)(?:::(\S+?))?\s+-\s+(\w+):?\s*(.*)"
)

# error_type 归一化：pytest -q 对断言失败输出 "assert xxx" 而非 "AssertionError: xxx"
_ERROR_TYPE_NORMALIZE: dict[str, str] = {
    "assert": "AssertionError",
}


@dataclass
class TestResult:
    """单个测试的执行结果（与 TestRunResult 互补）。"""
    __test__ = False
    test_id: str = ""
    passed: bool = False
    duration_ms: float = 0.0
    error: str = ""


class TestRunner:
    """测试运行器：subprocess 调 pytest + 解析输出。

    用法：
        runner = TestRunner()
        result = runner.run("tests/test_x.py")
        if not result.passed:
            for f in result.failures:
                print(f.test_id, f.error_type)
    """

    # 抑制 pytest 收集警告
    __test__ = False

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._results: list[TestResult] = []

    @property
    def timeout(self) -> int:
        return self._timeout

    def run(
        self,
        test_path: str,
        extra_args: list[str] | None = None,
        test_type: TestType = TestType.UNIT,
    ) -> TestRunResult:
        """运行测试。

        Args:
            test_path: 测试文件或目录路径。
            extra_args: 额外 pytest 参数（覆盖 test_type 默认参数之后追加）。
            test_type: 测试类型（P7 扩容）。默认 UNIT，按类型自动选择 pytest 标记。

        Returns:
            TestRunResult。
        """
        cmd = [
            "python", "-m", "pytest",
            test_path,
            "--tb=short",
            "-q",
            "--no-header",
        ]
        # P7 扩容：按测试类型注入 pytest 标记参数
        type_args = _TEST_TYPE_ARGS.get(test_type, [])
        if type_args:
            cmd.extend(type_args)
        if extra_args:
            cmd.extend(extra_args)

        logger.info("运行测试: %s", " ".join(cmd))
        t0 = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            logger.warning("测试超时（%ds）: %s", self._timeout, test_path)
            return TestRunResult(
                passed=False,
                duration_ms=int((time.time() - t0) * 1000),
                stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
                stderr=f"超时（{self._timeout}s）",
                returncode=-1,
            )
        except FileNotFoundError:
            logger.error("pytest 未安装或 python 不在 PATH")
            return TestRunResult(
                passed=False,
                stderr="pytest 未安装",
                returncode=-2,
            )

        duration_ms = int((time.time() - t0) * 1000)
        result = self.parse_output(stdout, stderr, returncode)
        result.duration_ms = duration_ms
        result.stdout = stdout
        result.stderr = stderr
        result.returncode = returncode
        return result

    def parse_output(
        self,
        stdout: str,
        stderr: str = "",
        returncode: int = 0,
    ) -> TestRunResult:
        """解析 pytest 输出。

        Args:
            stdout: pytest 标准输出。
            stderr: pytest 标准错误。
            returncode: pytest 返回码（0=全通过）。

        Returns:
            TestRunResult。
        """
        failures: list[TestFailure] = []

        # 解析 FAILED/ERROR 行
        for line in stdout.splitlines():
            m = _FAILED_PATTERN.match(line.strip())
            if m:
                test_path_full, test_name, error_type, error_msg = m.groups()
                # 归一化 error_type（assert → AssertionError）
                error_type = _ERROR_TYPE_NORMALIZE.get(error_type, error_type)
                test_name = test_name or "(collection)"
                failures.append(TestFailure(
                    test_id=f"{test_path_full}::{test_name}",
                    file=test_path_full,
                    test_name=test_name,
                    error_type=error_type,
                    error_message=(error_msg or "").strip(),
                ))

        # 解析统计行：例如 "5 passed in 0.12s" 或 "3 passed, 2 failed in 0.34s"
        passed_count, failed_count, error_count = self._parse_summary(stdout)
        total = passed_count + failed_count + error_count

        return TestRunResult(
            passed=(returncode == 0 and not failures),
            total=total,
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            failures=failures,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )

    def run_parallel(self, tests: list[str], workers: int = 4) -> list[TestResult]:
        """并行执行多个测试。
        Args:
            tests: 测试路径列表。
            workers: 并行数（默认 4）。
        Returns:
            TestResult 列表。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results: list[TestResult] = []
        def _run_single(tp: str) -> TestResult:
            t0 = time.time()
            try:
                r = self.run(tp)
                return TestResult(test_id=tp, passed=r.passed, duration_ms=r.duration_ms)
            except Exception as e:
                return TestResult(test_id=tp, passed=False, duration_ms=(time.time()-t0)*1000, error=str(e))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fut = {pool.submit(_run_single, t): t for t in tests}
            for f in as_completed(fut):
                results.append(f.result())
        self._results = results
        return results

    def generate_report(self, fmt: str = "json") -> str:
        """生成测试结果报告。
        Args:
            fmt: 'json' 或 'html'。
        Returns:
            报告字符串。
        """
        if fmt == "json":
            import json as _json
            return _json.dumps(
                [{"test_id": r.test_id, "passed": r.passed, "duration_ms": r.duration_ms, "error": r.error}
                 for r in self._results], ensure_ascii=False, indent=2,
            )
        elif fmt == "html":
            rows = "".join(
                f"<tr><td>{r.test_id}</td><td>{'PASS' if r.passed else 'FAIL'}</td>"
                f"<td>{r.duration_ms:.1f}ms</td><td>{r.error}</td></tr>"
                for r in self._results
            )
            total = len(self._results)
            passed = sum(1 for r in self._results if r.passed)
            return f"<html><body><h2>Test Report</h2><p>{passed}/{total} passed</p><table border=1>{rows}</table></body></html>"
        else:
            raise ValueError(f"不支持的格式: {fmt}")

    def _parse_summary(self, stdout: str) -> tuple[int, int, int]:
        """解析 pytest 末尾统计行。

        Returns:
            (passed, failed, error)
        """
        passed = 0
        failed = 0
        error = 0

        # 匹配 "N passed", "N failed", "N error"
        for line in stdout.splitlines():
            line = line.strip()
            # 例如："5 passed in 0.12s" / "3 passed, 2 failed in 0.34s" / "1 error in 0.1s"
            m_passed = re.search(r"(\d+)\s+passed", line)
            m_failed = re.search(r"(\d+)\s+failed", line)
            m_error = re.search(r"(\d+)\s+error", line)
            if m_passed:
                passed = int(m_passed.group(1))
            if m_failed:
                failed = int(m_failed.group(1))
            if m_error:
                error = int(m_error.group(1))

        return passed, failed, error
