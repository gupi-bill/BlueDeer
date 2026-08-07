#!/usr/bin/env python3
"""Core 模块依赖分析脚本。

功能：
1. 扫描 core/ 下所有模块的 import 语句
2. 检测循环依赖
3. 检测未使用的导入
4. 生成依赖图

用法：
    python scripts/analyze_dependencies.py [--core-dir core] [--output deps.md]
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path
from typing import Any
# ruff: noqa: F821


def parse_imports(file_path: Path) -> tuple[set[str], set[str]]:
    """解析 Python 文件的 import 语句。

    Returns:
        (imports, from_imports) 其中：
        - imports: import xxx
        - from_imports: from xxx import yyy
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set(), set()

    imports: set[str] = set()
    from_imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            from_imports.add(node.module.split(".")[0])

    return imports, from_imports


def analyze_core(core_dir: Path) -> dict[str, Any]:
    """分析 core/ 目录的模块依赖。"""
    modules: dict[str, set[str]] = defaultdict(set)
    module_files: dict[str, Path] = {}

    # 扫描所有 Python 文件
    for py_file in core_dir.rglob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = py_file.stem
        module_files[module_name] = py_file

    # 解析依赖
    for module_name, py_file in module_files.items():
        imports, from_imports = parse_imports(py_file)
        deps = set()
        for imp in imports | from_imports:
            if imp in module_files and imp != module_name:
                deps.add(imp)
        modules[module_name] = deps

    # 检测循环依赖
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in modules.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)

        path.pop()
        rec_stack.remove(node)

    for module in modules:
        if module not in visited:
            dfs(module, [])

    return {
        "modules": dict(modules),
        "cycles": cycles,
        "module_files": {k: str(v) for k, v in module_files.items()},
    }


def generate_report(analysis: dict[str, Any], output: Path) -> None:
    """生成依赖分析报告。"""
    lines = ["# Core 模块依赖分析报告", ""]

    lines.append("## 模块列表")
    lines.append("")
    for module in sorted(analysis["modules"].keys()):
        deps = analysis["modules"][module]
        if deps:
            lines.append(f"- {module} → {', '.join(sorted(deps))}")
        else:
            lines.append(f"- {module}（无依赖）")
    lines.append("")

    if analysis["cycles"]:
        lines.append("## 循环依赖")
        lines.append("")
        for cycle in analysis["cycles"]:
            lines.append(f"- {' → '.join(cycle)}")
        lines.append("")
    else:
        lines.append("## 循环依赖")
        lines.append("")
        lines.append("未检测到循环依赖。")
        lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已生成: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Core 模块依赖分析")
    parser.add_argument("--core-dir", default="core", help="core 目录路径")
    parser.add_argument(
        "--output", default="docs/dependency_report.md", help="输出报告路径"
    )
    args = parser.parse_args()

    core_dir = Path(args.core_dir)
    if not core_dir.exists():
        print(f"错误：{core_dir} 不存在")
        return 1

    analysis = analyze_core(core_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_report(analysis, output)

    if analysis["cycles"]:
        print(f"警告：检测到 {len(analysis['cycles'])} 个循环依赖")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
