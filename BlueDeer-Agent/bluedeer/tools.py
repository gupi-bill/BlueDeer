"""内置工具注册表：模型只能提议调用，真正执行由代码把关。"""

import ast
import json
import operator
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bluedeer.config import ROOT_DIR


@dataclass
class Tool:
    name: str
    description: str
    params_hint: str
    func: Callable[[dict], str]


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_calc(node):
    if isinstance(node, ast.Expression):
        return _safe_calc(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_calc(node.left), _safe_calc(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_calc(node.operand))
    raise ValueError("只允许纯算术表达式")


def calc(params: dict) -> str:
    expr = str(params.get("expression", "")).strip()
    if not expr:
        return "[calc 错误] 缺少 expression 参数"
    try:
        result = _safe_calc(ast.parse(expr, mode="eval"))
        return f"{expr} = {result}"
    except Exception as e:
        return f"[calc 错误] {e}"


def now(params: dict) -> str:
    fmt = str(params.get("format", "%Y-%m-%d %H:%M:%S"))
    try:
        return time.strftime(fmt)
    except Exception as e:
        return f"[now 错误] {e}"


def read_file(params: dict) -> str:
    rel = str(params.get("path", ""))
    p = (ROOT_DIR / rel).resolve() if rel else None
    if not p or ".." in Path(rel).parts or not str(p).startswith(str(ROOT_DIR)):
        return "[read_file 错误] 路径越界"
    if not p.exists():
        return f"[read_file 错误] 文件不存在：{rel}"
    try:
        text = p.read_text(encoding="utf-8")
        return text[:4000] + ("\n…（已截断）" if len(text) > 4000 else "")
    except Exception as e:
        return f"[read_file 错误] {e}"


def write_file(params: dict) -> str:
    rel = str(params.get("path", ""))
    content = params.get("content", "")
    if not rel:
        return "[write_file 错误] 缺少 path"
    parts = Path(rel).parts
    p = (ROOT_DIR / rel).resolve()
    if ".." in parts or not str(p).startswith(str(ROOT_DIR)):
        return "[write_file 错误] 路径越界"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        p.write_text(str(content), encoding="utf-8")
        return f"已写入 {rel}（{p.stat().st_size} 字节）"
    except Exception as e:
        return f"[write_file 错误] {e}"


def list_dir(params: dict) -> str:
    rel = str(params.get("path", "."))
    p = (ROOT_DIR / rel).resolve()
    if ".." in Path(rel).parts or not str(p).startswith(str(ROOT_DIR)):
        return "[list_dir 错误] 路径越界"
    if not p.is_dir():
        return f"[list_dir 错误] 不是目录：{rel}"
    entries = []
    for child in sorted(p.iterdir())[:100]:
        tag = "目录" if child.is_dir() else f"{child.stat().st_size}B"
        entries.append(f"{child.name}/  {tag}" if child.is_dir() else f"{child.name}  {tag}")
    return "\n".join(entries) or "（空目录）"


def run_python(params: dict) -> str:
    code = str(params.get("code", ""))
    if not code.strip():
        return "[run_python 错误] 缺少 code"
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT_DIR),
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        result = out
        if r.returncode != 0:
            result = f"[退出码 {r.returncode}] {out}\n{err}".strip()
        elif err:
            result = f"{out}\n[stderr] {err}"
        return (result or "（无输出）")[:4000]
    except subprocess.TimeoutExpired:
        return "[run_python 错误] 执行超时（>10s）"
    except Exception as e:
        return f"[run_python 错误] {e}"


def http_get(params: dict) -> str:
    url = str(params.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return "[http_get 错误] 只支持 http/https URL"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BlueDeerAgent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return (body[:4000] + ("\n…（已截断）" if len(body) > 4000 else "")) or "（空响应）"
    except Exception as e:
        return f"[http_get 错误] {e}"


DEFAULT_TOOLS = [
    Tool("calc", "计算纯算术表达式", '{"expression": "1+2*3"}', calc),
    Tool("now", "获取当前时间，format 为 strftime 格式", '{"format": "%Y-%m-%d %H:%M:%S"}', now),
    Tool(
        "read_file",
        "读取项目内文本文件（限项目根目录内）",
        '{"path": "README.md"}',
        read_file,
    ),
    Tool(
        "write_file",
        "写入文本到项目内文件（限项目根目录内）",
        '{"path": "data/out.txt", "content": "内容"}',
        write_file,
    ),
    Tool("list_dir", "列出项目内目录内容", '{"path": "."}', list_dir),
    Tool("run_python", "运行一段 Python 代码并返回输出（10s 超时）", '{"code": "print(1+1)"}', run_python),
    Tool("http_get", "GET 一个 http/https 地址并返回前 4000 字符", '{"url": "https://example.com"}', http_get),
]

_TOOL_INDEX = {t.name: t for t in DEFAULT_TOOLS}


def build_tools(enabled: list | None = None) -> dict:
    """enabled 为空/None 表示全量；名字不认识就跳过。"""
    if not enabled:
        return dict(_TOOL_INDEX)
    return {n: _TOOL_INDEX[n] for n in enabled if n in _TOOL_INDEX}


def catalog(tools: dict) -> str:
    lines = []
    for t in tools.values():
        lines.append(f"- TOOL {t.name}: {t.description}; ARGS 示例 {t.params_hint}")
    return "\n".join(lines)
