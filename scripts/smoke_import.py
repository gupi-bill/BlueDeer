"""全模块冒烟套件：语法检查 + import 冒烟。

用法:
    python scripts/smoke_import.py            # 全量
    python scripts/smoke_import.py core       # 只跑 core/
    python scripts/smoke_import.py --quick    # 只跑顶层 + core/ 顶层文件

判定标准:
    - 语法: ast.parse 每个 .py
    - import: importlib.import_module，无副作用要求（纯导入）
退出码: 0 = 全绿, 1 = 有失败
"""
from __future__ import annotations

import ast
import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", "venv", ".venv", "odysseus", "node_modules"}
SKIP_PREFIXES = ("test_", "test_runner")
SKIP_FILES = {"setup.py", "conftest.py"}

# 顶层模块必须在项目根 import（web_server:app 等）
sys.path.insert(0, str(ROOT))


def iter_py_files(scope: str | None = None) -> list[Path]:
    roots: list[Path] = [ROOT]
    if scope:
        roots = [ROOT / scope]
    files: list[Path] = []
    for root in roots:
        for p in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.name.startswith(SKIP_PREFIXES) or p.name in SKIP_FILES:
                continue
            files.append(p)
    return files


def to_module_name(p: Path) -> str:
    rel = p.relative_to(ROOT)
    parts = list(rel.parts[:-1]) + [rel.stem]
    return ".".join(parts)


def main() -> int:
    scope = None
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        scope = args[0]

    files = iter_py_files(scope)
    syntax_fail: list[str] = []
    import_fail: list[tuple[str, str]] = []
    ok: list[str] = []

    for f in files:
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            syntax_fail.append(f"{f.relative_to(ROOT)}:{e.lineno} {e.msg}")
            continue

        mod = to_module_name(f)
        try:
            importlib.import_module(mod)
            ok.append(mod)
        except Exception as e:
            import_fail.append((mod, f"{type(e).__name__}: {e}"))

    total = len(files)
    print(f"== 冒烟结果: {len(ok)} OK / {len(import_fail)} import失败 / {len(syntax_fail)} 语法失败 (共 {total}) ==")
    if syntax_fail:
        print("\n--- 语法失败 ---")
        for s in syntax_fail:
            print(f"  [语法] {s}")
    if import_fail:
        print("\n--- import 失败 ---")
        for mod, err in import_fail:
            print(f"  [导入] {mod} -> {err}")

    bad = len(syntax_fail) + len(import_fail)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
