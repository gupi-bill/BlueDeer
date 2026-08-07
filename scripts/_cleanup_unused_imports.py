"""006-24: 清理未使用 import（基于审计报告 + AST 精确定位）。v2"""

import logging

logger = logging.getLogger(__name__)
import ast
import os
import re

BASE = r"C:\Users\a\Desktop\vibe coding\BlueDeer"
REPORT = os.path.join(BASE, "reports", "006-24_dead_code_audit.md")
SKIP_FILES = {"__init__.py"}


def module_name(path):
    rel = os.path.relpath(path, BASE).replace("\\", "/")[:-3]
    return rel.replace("/", ".")


def is_type_checking_block(tree, lineno):
    """该行是否位于 if TYPE_CHECKING: 块内。"""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ) and node.lineno <= lineno <= (getattr(node, "end_lineno", lineno) or lineno):
            return True
    return False


def remove_names_from_line(src_lines, lineno, names, path):
    """返回 (new_line, del_end)。new_line=None=无法处理；del_end=删除到该行。"""
    line = src_lines[lineno - 1]
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]
    if stripped.startswith("import "):
        parts = [p.strip() for p in stripped[len("import ") :].split(",")]
        keep = [
            p for p in parts if p.split(" as ")[0].split(".")[0].strip() not in names
        ]
        if not keep:
            return "", None
        return indent + "import " + ", ".join(keep) + "\n", None
    if stripped.startswith("from "):
        m = re.match(r"^from\s+(\S+)\s+import\s+(.+)$", stripped)
        if not m:
            return None, None
        mod, body = m.group(1), m.group(2)
        if mod == module_name(path):
            return "", None
        if body.startswith("("):
            buf = [body]
            idx = lineno
            while ")" not in "".join(buf) and idx < len(src_lines):
                idx += 1
                buf.append(src_lines[idx - 1])
            full = "".join(buf)
            inner = full[full.index("(") + 1 : full.rindex(")")]
            parts = [p.strip().rstrip(",") for p in inner.split(",") if p.strip()]
            keep = [p for p in parts if p.split(" as ")[0].strip() not in names]
            if not keep:
                return "", idx
            new_body = (
                "(\n" + "".join(f"{indent}    {p},\n" for p in keep) + indent + ")"
            )
            return f"{indent}from {mod} import {new_body}\n", idx
        parts = [p.strip() for p in body.split(",")]
        keep = [p for p in parts if p.split(" as ")[0].strip() not in names]
        if not keep:
            return "", None
        return indent + f"from {mod} import {', '.join(keep)}\n", None
    return None, None


def main():
    entries = []
    in_sec1 = False
    for line in open(REPORT, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("## "):
            in_sec1 = line.startswith("## 1.")
            continue
        if not in_sec1:
            continue
        m = re.match(r"^- `([^:]+):(\d+)`  `(.+)`$", line)
        if m:
            entries.append((m.group(1), int(m.group(2)), m.group(3)))

    by_file = {}
    for rel, lineno, name in entries:
        rel = rel.replace("\\", "/")
        if os.path.basename(rel) in SKIP_FILES:
            continue
        by_file.setdefault(rel, {}).setdefault(lineno, set()).add(name)

    total_removed = 0
    changed = []
    for rel, lines_map in sorted(by_file.items()):
        path = os.path.join(BASE, rel)
        src_lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
        try:
            tree = ast.parse("".join(src_lines))
        except SyntaxError:
            print(f"SKIP {rel} (原文件语法错误)")
            continue
        modified = False
        # 归并续行条目到所属多行 import 首行
        merged = {}
        for lineno in sorted(lines_map):
            names = lines_map[lineno]
            if lineno > len(src_lines):
                print(f"  {rel}:{lineno} - {sorted(names)} (行号越界,跳过)")
                continue
            line = src_lines[lineno - 1].strip()
            if line.startswith(("import ", "from ")):
                merged.setdefault(lineno, set()).update(names)
                continue
            j = lineno
            while j > 1 and "(" not in src_lines[j - 1]:
                j -= 1
            if j < lineno and "import (" in src_lines[j - 1]:
                merged.setdefault(j, set()).update(names)
            else:
                merged.setdefault(lineno, set()).update(names)
        for lineno in sorted(merged, reverse=True):
            if is_type_checking_block(tree, lineno):
                print(f"  {rel}:{lineno} - 跳过(TYPE_CHECKING)")
                continue
            names = lines_map[lineno]
            new_line, del_end = remove_names_from_line(src_lines, lineno, names, path)
            if new_line is None:
                print(f"SKIP {rel}:{lineno} {sorted(names)} (无法处理)")
                continue
            if del_end is not None:
                for i in range(lineno - 1, del_end):
                    src_lines[i] = ""
                src_lines[lineno - 1] = new_line
                total_removed += len(names)
                modified = True
                print(f"  {rel}:{lineno}-{del_end} - {sorted(names)} (重写)")
                continue
            if new_line != src_lines[lineno - 1]:
                src_lines[lineno - 1] = new_line
                total_removed += len(names)
                modified = True
                print(f"  {rel}:{lineno} - {sorted(names)}")
        if modified:
            try:
                ast.parse("".join(src_lines))
            except SyntaxError as e:
                print(f"  !! SYNTAX {rel}: {e} — 回滚")
                continue
            open(path, "w", encoding="utf-8", newline="").writelines(src_lines)
            changed.append(rel)

    print(f"\n清理完成: {total_removed} 个名字, {len(changed)} 个文件")
    print("变更文件:", ", ".join(changed))


if __name__ == "__main__":
    main()
