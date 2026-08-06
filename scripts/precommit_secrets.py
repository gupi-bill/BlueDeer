"""pre-commit hook: scan staged/staged-any .py for secret leaks via SecurityScanner.

Exit code 0 = clean, 1 = secret-like tokens found (block commit).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.security as sec

# 扫描规则自身文件：命中的是规则模式串，不是真实威胁
SELF_FILES = {
    "security.py",
    "security_scanner.py",
    "security_guard.py",
    "security_report.py",
}

# 已知误报白名单：(文件名, 威胁类型)。
# security.py 的 port=80 是规则模式串自身；email_digest 是从 config 读 password 的合法用法。
KNOWN_FALSE_POSITIVES = {
    ("security.py", "hardcoded:port"),
    ("email_digest.py", "secret_leak:password"),
}


def main() -> int:
    base = os.path.join(os.path.dirname(__file__), "..")
    scanner = sec.SecurityScanner()
    leakers = 0
    for root, _dirs, files in os.walk(os.path.abspath(os.path.join(base, "core"))):
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
            threats = scanner.scan_secret_leak(text) + scanner.scan_hardcoded(text)
            for t in threats:
                if (fn, t.threat_type) in KNOWN_FALSE_POSITIVES:
                    continue
                print(f"{fn}: [{t.threat_type}] {t.matched}")
                leakers += 1
    if leakers:
        print(f"pre-commit secrets scan FAILED: {leakers} leak candidate(s)")
        return 1
    print("pre-commit secrets scan PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
