"""006-24: dead code / unused imports audit (ast-based, no deps)."""

import logging

logger = logging.getLogger(__name__)
import ast
import os
from collections import Counter

BASE = r"<WORKSPACE_DIR>\BlueDeer"
AUDIT_DIRS = ["core", "modules", "cli", "scripts", "tools"]
REF_DIRS = AUDIT_DIRS + ["tests", "launchers"]


def py_files(dirs):
    out = []
    for d in dirs:
        root = os.path.join(BASE, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in filenames:
                if fn.endswith(".py"):
                    out.append(os.path.join(dirpath, fn))
    return out


class Analyzer:
    def __init__(self, path):
        self.path = path
        self.src = open(path, encoding="utf-8").read()
        self.tree = ast.parse(self.src)
        self.imports = {}  # name -> (lineno, kind)
        self.used = Counter()  # Name.id + Attribute.attr counts (imports excluded)
        self.top_defs = []  # (name, lineno, kind)
        self.all_names = []  # __all__ strings
        self.import_nodes = set()
        self.decorated = set()  # 有装饰器的顶层 def/class 名（框架注册型）

    def run(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                self.import_nodes.add(node)
                for a in node.names:
                    name = a.asname or a.name.split(".")[0]
                    self.imports[name] = (node.lineno, "import")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                self.import_nodes.add(node)
                for a in node.names:
                    name = a.asname or a.name
                    if name != "*":
                        self.imports[name] = (node.lineno, "from")
            elif isinstance(node, ast.Name):
                self.used[node.id] += 1
            elif isinstance(node, ast.Attribute):
                self.used[node.attr] += 1
        # strip counts contributed by import nodes themselves
        for node in self.import_nodes:
            for n in ast.walk(node):
                if isinstance(n, ast.Name):
                    self.used[n.id] -= 1
                elif isinstance(n, ast.Attribute):
                    self.used[n.attr] -= 1
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.decorator_list:
                    self.decorated.add(node.name)
                self.top_defs.append((node.name, node.lineno, type(node).__name__))
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for el in node.value.elts:
                                if isinstance(el, ast.Constant) and isinstance(
                                    el.value, str
                                ):
                                    self.all_names.append(el.value)
        # def names are not Name nodes; strip self-reference counts from decorators etc.
        return self


def main():
    analyzers = {}
    ref_used = Counter()
    for p in py_files(REF_DIRS):
        try:
            an = Analyzer(p).run()
        except SyntaxError as e:
            print(f"SYNTAX {p}: {e}")
            continue
        analyzers[p] = an
        ref_used.update(an.used)
        ref_used.update(an.all_names)

    lines = []
    lines.append("# 006-24 Dead Code Audit Report")
    lines.append("")
    lines.append(f"- 扫描文件数: {len(analyzers)}")
    lines.append("")

    # ---- 1. unused imports ----
    lines.append("## 1. 未使用 import")
    lines.append("")
    n_unused = 0
    for p, an in sorted(analyzers.items()):
        if not p.replace("\\", "/").startswith(
            tuple(BASE.replace("\\", "/") + "/" + d for d in AUDIT_DIRS)
        ):
            continue
        rel = os.path.relpath(p, BASE)
        bad = []
        for name, (lineno, kind) in sorted(an.imports.items(), key=lambda x: x[1][0]):
            if an.used[name] <= 0:
                bad.append((lineno, name))
        for lineno, name in bad:
            n_unused += 1
            lines.append(f"- `{rel}:{lineno}`  `{name}`")
    lines.append("")
    lines.append(f"未使用 import 总数: {n_unused}")
    lines.append("")

    # ---- 2. dead top-level defs ----
    lines.append("## 2. 疑似死代码（模块级 def/class，全项目 0 引用）")
    lines.append("")
    n_dead = 0
    for p, an in sorted(analyzers.items()):
        if not p.replace("\\", "/").startswith(
            tuple(BASE.replace("\\", "/") + "/" + d for d in AUDIT_DIRS)
        ):
            continue
        rel = os.path.relpath(p, BASE)
        for name, lineno, kind in an.top_defs:
            if name.startswith("_") or name in ("main",) or name in an.decorated:
                continue
            if ref_used[name] <= 0:
                n_dead += 1
                lines.append(f"- `{rel}:{lineno}`  `{kind} {name}`")
    lines.append("")
    lines.append(f"疑似死代码总数: {n_dead}")
    lines.append("")
    lines.append(
        "> 注: 动态引用（getattr/globals()[name]/字符串调用）无法静态识别，清理前需人工复核。"
    )

    report = "\n".join(lines)
    out = os.path.join(BASE, "reports", "006-24_dead_code_audit.md")
    open(out, "w", encoding="utf-8").write(report)
    print(f"unused imports: {n_unused}, dead defs: {n_dead}")
    print(f"report -> {out}")
    print()
    # console: show up to 60 lines of each section
    for sec in report.split("## ")[1:]:
        head, *body = sec.split("\n")
        print(f"## {head}")
        shown = [l for l in body if l.strip().startswith("-")]
        for l in shown[:60]:
            print(l)
        if len(shown) > 60:
            print(f"  ... 另有 {len(shown)-60} 条见报告")
        print()


if __name__ == "__main__":
    main()
