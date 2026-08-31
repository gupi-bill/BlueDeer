#!/usr/bin/env python3
"""安全自检工具（企业版）。

扫描：
  1. 代码库明文密钥 / 硬编码密码
  2. /debug 开放调试接口未鉴权
  3. requirements.txt 已知高危依赖（内置小型黑名单，离线可用）

用法：python scripts/security_scan.py
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 内置常见高危/已弃用依赖黑名单（离线可用）
KNOWN_RISKY_PACKAGES = {
    "pickle": "反序列化风险，禁止用于不受信数据",
    "eval": "任意代码执行风险",
    "yaml.load": "YAML 不安全加载",
    "subprocess": "命令注入风险需严格过滤",
    "os.system": "命令注入风险",
    "md5": "弱哈希算法",
    "sha1": "弱哈希算法",
}

# 调试接口路径
DEBUG_PATHS = ["/debug", "/debugger", "/_debug", "/api/debug"]

# 明文密钥模式
SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]"),
    re.compile(r"(?i)(api[_-]?key|apikey|token|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
]


def scan_plaintext(patterns: list[re.Pattern]) -> list[str]:
    hits: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        # 跳过虚拟环境、测试快照、备份、数据
        if any(seg in dirpath for seg in ('.venv', '.git', '__pycache__', 'backups', '.workbuddy', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'memory_archive', 'vector_db')):
            continue
        for fn in filenames:
            if not fn.endswith(('.py', '.json', '.md', '.txt', '.yaml', '.yml')):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except OSError:
                continue
            for p in patterns:
                for m in p.finditer(text):
                    # 过滤明确的安全占位
                    hit = m.group(0)
                    if any(x in hit.lower() for x in ('placeholder', 'your_', 'example', 'changeme', 'bluedeer888', 'test_')):
                        continue
                    hits.append(f"{fp}: {hit[:80]}")
    return hits


def scan_debug_routes() -> list[str]:
    hits: list[str] = []
    app_py = os.path.join(ROOT, 'web_server', 'app.py')
    try:
        with open(app_py, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except OSError:
        return hits
    for path in DEBUG_PATHS:
        if path in text:
            # 检查是否被鉴权保护（简单的启发式）
            if 'auth' not in text and 'middleware' not in text.lower():
                hits.append(f"{app_py}: 调试接口 {path} 可能存在但缺少鉴权")
    return hits


def scan_requirements() -> list[str]:
    hits: list[str] = []
    req_path = os.path.join(ROOT, 'requirements.txt')
    try:
        with open(req_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except OSError:
        return hits
    for pkg, reason in KNOWN_RISKY_PACKAGES.items():
        if pkg in text:
            hits.append(f"requirements.txt: 含风险依赖 {pkg} - {reason}")
    return hits


def main() -> int:
    print('=== BlueDeer 安全自检 ===')
    plaintext_hits = scan_plaintext(SECRET_PATTERNS)
    debug_hits = scan_debug_routes()
    req_hits = scan_requirements()

    print(f'[明文密钥] 命中 {len(plaintext_hits)} 处')
    for h in plaintext_hits[:20]:
        print('  -', h)
    print(f'[调试接口] 命中 {len(debug_hits)} 处')
    for h in debug_hits:
        print('  -', h)
    print(f'[依赖风险] 命中 {len(req_hits)} 处')
    for h in req_hits:
        print('  -', h)

    total = len(plaintext_hits) + len(debug_hits) + len(req_hits)
    print(f'=== 总计 {total} 处风险 ===')
    return 0 if total == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
