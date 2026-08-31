"""BlueDeer 总控台前端。

读取 templates/project_hub.html，作为 BlueDeer 各子模块的统一框架入口。
"""

from __future__ import annotations

import os


def render_hub() -> str:
    """读取总控台 HTML 模板并返回完整字符串。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "templates", "project_hub.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>BlueDeer 总控台</title></head><body><h1>模板缺失</h1><p>未找到 templates/project_hub.html</p></body></html>"


__all__ = ["render_hub"]
