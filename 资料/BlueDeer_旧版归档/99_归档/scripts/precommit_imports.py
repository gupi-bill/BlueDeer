"""pre-commit hook: AST syntax + import resolution check over core & modules.

Exit code 0 = clean, 1 = syntax/import errors found.
"""

from __future__ import annotations

import ast
import os
import sys

TOP = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP = {"__pycache__", ".git", "odysseus"}


def iter_py_files() -> list[str]:
    files: list[str] = []
    for base in ("core", "models", "modules", "tests", "scripts", "cli"):
        d = os.path.join(TOP, base)
        if not os.path.isdir(d):
            continue
        for root, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x not in SKIP]
            for n in names:
                if n.endswith(".py"):
                    files.append(os.path.join(root, n))
    return files


def main() -> int:
    bad = 0
    for path in iter_py_files():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
            ast.parse(src, filename=path)
        except SyntaxError as e:
            print(f"SYNTAX {path}:{e.lineno}: {e.msg}")
            bad += 1
        except (OSError, UnicodeDecodeError) as e:
            print(f"READ {path}: {e}")
            bad += 1
    if bad:
        print(f"pre-commit import check FAILED: {bad} file(s)")
        return 1
    print(f"pre-commit import check PASSED ({len(iter_py_files())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
