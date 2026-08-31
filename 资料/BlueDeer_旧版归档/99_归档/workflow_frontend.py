"""BlueDeer 可视化工作流编辑器前端。

零依赖纯前端：读取 templates/workflow.html（原生 SVG + JS，无 React、无 npm 构建）。
只提供一个 render_workflow()，被 core/game_router.py 的 /workflow 路由调用。
"""

from __future__ import annotations

import os


def render_workflow() -> str:
    """读取零依赖工作流编辑器 HTML 模板并返回完整字符串。

    Returns:
        templates/workflow.html 的完整内容；若模板缺失，返回一个极简错误页。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "templates", "workflow.html")

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>BlueDeer 工作流编辑器</title></head><body><h1>模板缺失</h1><p>未找到 templates/workflow.html</p></body></html>"


__all__ = ["render_workflow"]
