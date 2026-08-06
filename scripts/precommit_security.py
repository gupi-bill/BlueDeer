"""pre-commit hook: run core.security.SecurityScanner over .py files.

Aggregates threats across the tree, skips the scanner's own rule files,
then judges acceptability with SecurityReportBuilder.is_acceptable
(fail_on_high / max_medium / max_total).

Exit code 0 = acceptable, 1 = blocked.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.security as sec
from core.security_report import SecurityReportBuilder, SecurityThresholds

# 扫描规则自身文件：命中的是规则模式串，不是真实威胁
SELF_FILES = {
    "security.py",
    "security_scanner.py",
    "security_guard.py",
    "security_report.py",
}

# 已知误报白名单：(文件名, 威胁类型)。审过的合法用法/扫描器自身字符串/仿真生态随机。
KNOWN_FALSE_POSITIVES = {
    # tool_registry 安全检查自身的 "eval(" / "exec(" 字符串检测
    ("tool_registry.py", "unsafe_api:eval"),
    ("tool_registry.py", "unsafe_api:exec"),
    # agentic_loop 里的 "...\\n" 字符串字面量（SECURITY_REVIEW.md 已记录，已删故不再出现）
    ("agentic_loop.py", "path_traversal"),
    # bplus_tree pickle.load( —— 自管数据库文件的持久化反序列化（本地数据非外部输入）
    ("bplus_tree.py", "unsafe_api:pickle"),
    # email_digest 从 config 读 password 传给 smtp login（正常用法，非硬编码）
    ("email_digest.py", "secret_leak:password"),
    # shell_executor 是工具执行器本体，shell=True 为其设计语义
    ("shell_executor.py", "unsafe_api:subprocess_shell"),
    # log_token/exception_secret：记录 token 用量统计或 ValueError 消息，非密钥泄露
    ("circuit_breaker.py", "undisinfected_log:log_token"),
    ("debugger.py", "undisinfected_log:log_token"),
    ("git_ops.py", "undisinfected_log:log_token"),
    ("reward_settler.py", "undisinfected_log:log_token"),
    ("task_dispatcher.py", "undisinfected_log:log_token"),
    ("token_auditor.py", "undisinfected_log:log_token"),
    ("token_bucket.py", "undisinfected_log:exception_secret"),
}


def main() -> int:
    base = os.path.join(os.path.dirname(__file__), "..")
    scanner = sec.SecurityScanner()
    target = os.path.abspath(os.path.join(base, "core"))
    total: list[sec.Threat] = []
    for root, _dirs, files in os.walk(target):
        if "__pycache__" in root:
            continue
        for fn in files:
            if not fn.endswith(".py") or fn in SELF_FILES:
                continue
            path = os.path.join(root, fn)
            try:
                text = open(path, "r", encoding="utf-8").read()
            except OSError:
                continue
            report = scanner.scan_all(text, target=fn)
            if report.threats:
                for t in report.threats:
                    if (fn, t.threat_type) in KNOWN_FALSE_POSITIVES:
                        continue
                    print(f"{fn}: [{t.threat_type}] risk={t.risk} {t.matched[:60]}")
                    total.append(t)
    builder = SecurityReportBuilder(scanner, SecurityThresholds())
    report = sec.SecurityReport(target="core/**", threats=total)
    ok, reason = builder.is_acceptable(report)
    if not ok:
        print(f"pre-commit security scan FAILED: {len(total)} threat(s) -- {reason}")
        return 1
    print(
        f"pre-commit security scan PASSED: {len(total)} threat(s) within thresholds ({reason})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
