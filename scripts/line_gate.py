"""语法巡逻 + 2000 行门禁：守护代码库健康，防止巨型文件继续膨胀。

用法:
    python scripts/line_gate.py               # 语法巡逻 + 行数门禁
    python scripts/line_gate.py --threshold 3000   # 自定义阈值

规则:
    1. 语法巡逻: 全项目 *.py 用 ast 解析，任何 SyntaxError 即失败。
    2. 行数门禁: 超过阈值(默认 2000 行)的文件必须登记在豁免清单里，
       未登记的超限文件视为新增膨胀，门禁失败。
    3. 豁免范围: odysseus/ 是外部项目目录不参与门禁；已在册的
       legacy 超大文件允许存在但会提示建议拆分。

退出码: 0 = 全绿(可容忍在册豁免), 1 = 语法错误或新增超限
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 外部项目目录：不参与语法巡逻与行数门禁
EXTERNAL_DIRS = {"odysseus", "hermes", "ast-grep-base", "ast-grep-bin"}

# 在册 legacy 超大文件（相对 ROOT 的路径）：
# 历史遗留巨型文件，允许存在但属于拆分候选，新增超限文件不允许。
LEGACY_LARGE = {
    "game_frontend.py",
    "web_server.py",
    "core/digital_life/digital_life_form.py",
}

# 扫描时跳过的杂物目录
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "data"}


def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT)
        if any(part in EXTERNAL_DIRS for part in rel.parts):
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(p)
    return files


def count_lines(p: Path) -> int:
    n = 0
    with p.open(encoding="utf-8", errors="replace") as fh:
        for _ in fh:
            n += 1
    return n


def main() -> int:
    threshold = 2000
    args = sys.argv[1:]
    if "--threshold" in args:
        idx = args.index("--threshold")
        if idx + 1 < len(args):
            threshold = int(args[idx + 1])

    files = iter_py_files()
    syntax_errors: list[str] = []
    over_limit: list[tuple[int, str]] = []
    unregistered: list[tuple[int, str]] = []

    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            syntax_errors.append(f"{rel}:{e.lineno} {e.msg}")
        n = count_lines(p)
        if n > threshold:
            over_limit.append((n, rel))
            if rel not in LEGACY_LARGE:
                unregistered.append((n, rel))

    print("== 语法巡逻 ==")
    print(f"  扫描文件: {len(files)}，语法错误: {len(syntax_errors)}")
    for e in syntax_errors:
        print(f"  [FAIL] {e}")

    print(f"== 行数门禁 (阈值 {threshold}) ==")
    print(f"  超限文件: {len(over_limit)}")
    for n, rel in sorted(over_limit, reverse=True):
        tag = "legacy 豁免" if rel in LEGACY_LARGE else "未登记!"
        print(f"  {n:>6} 行  {rel}  [{tag}]")
    if unregistered:
        for n, rel in unregistered:
            print(f"  [FAIL] 新增超限未登记: {rel} ({n} 行)")

    total = sum(count_lines(p) for p in files)
    print(f"  项目总行数: {total}")

    failed = bool(syntax_errors) or bool(unregistered)
    print(f"== 结果: {'FAIL' if failed else 'PASS'} ==")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
