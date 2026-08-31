"""内置工具注册表：模型只能提议调用，真正执行由代码把关。

办公重型工具集：
- code_review: 代码审查（静态分析 + 规范检查）
- search_code: 全局搜索（grep-like）
- run_tests: 运行测试套件
- gen_report: 生成办公报告（会议纪要/周报/需求文档）
- git_status: Git 状态/分支/变更
- run_command: 执行任意 shell 命令（受限）
- diff_files: 对比文件差异
- count_lines: 统计代码行数
"""

import ast
import json
import operator
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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


# ==================== 办公重型工具 ====================

def code_review(params: dict) -> str:
    """代码审查：对指定文件进行静态分析，找出 bug、规范问题、性能隐患。"""
    path = str(params.get("path", ""))
    if not path:
        return "[code_review 错误] 缺少 path 参数"
    full = ROOT_DIR / path
    if not full.exists() or not full.is_file():
        return f"[code_review 错误] 文件不存在：{path}"
    try:
        text = full.read_text(encoding="utf-8")
    except Exception as e:
        return f"[code_review 错误] 读取失败：{e}"

    issues = []
    lines = text.splitlines()
    # 1. 长行检查
    for i, line in enumerate(lines, 1):
        if len(line) > 120:
            issues.append(f"行 {i}: 行过长 ({len(line)} 字符)，建议拆分")
    # 2. 未使用变量（简单检查）
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("'''") or stripped.startswith('"""'):
            continue
        # 检查未使用的 import（简化版）
        m = re.match(r"import\s+(\w+)", stripped)
        if m:
            var = m.group(1)
            if var not in text[text.index(stripped):].replace(stripped, "", 1):
                issues.append(f"行 {i}: '{var}' 可能未使用")
    # 3. 硬编码路径
    for i, line in enumerate(lines, 1):
        if re.search(r'["\'][A-Za-z]:[/\\]', line):
            issues.append(f"行 {i}: 发现硬编码绝对路径，建议用 Path 替代")
    # 4. 裸 except
    for i, line in enumerate(lines, 1):
        if re.search(r"except\s*:", line.strip()):
            issues.append(f"行 {i}: 裸 except 建议指定异常类型")
    # 5. print 调试
    for i, line in enumerate(lines, 1):
        if re.search(r"\bprint\s*\(", line.strip()):
            issues.append(f"行 {i}: 发现 print() 调试语句")
    # 6. 魔法数字
    for i, line in enumerate(lines, 1):
        m = re.search(r"(?<![a-zA-Z_])(\d+\.\d+|\d{3,})", line)
        if m and "def " not in line and "#" not in line.split(m.group(0))[0]:
            issues.append(f"行 {i}: 发现魔法数字 {m.group(0)}，建议提取为常量")

    if not issues:
        return f"✅ {path} 审查通过（{len(lines)} 行），未发现明显问题"
    return f"📋 {path} 审查报告（{len(lines)} 行，{len(issues)} 个问题）:\n" + "\n".join(f"  {iss}" for iss in issues[:30])


def search_code(params: dict) -> str:
    """全局搜索：grep-like，在项目中搜索匹配文本。"""
    pattern = str(params.get("pattern", ""))
    path_filter = str(params.get("path_filter", "."))
    if not pattern:
        return "[search_code 错误] 缺少 pattern 参数"
    full = (ROOT_DIR / path_filter).resolve()
    if not full.startswith(str(ROOT_DIR)):
        return "[search_code 错误] 路径越界"
    results = []
    count = 0
    for root, dirs, files in __import__("os").walk(full):
        # 跳过隐藏目录和 __pycache__
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != ".venv"]
        for f in files:
            if f.endswith((".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".yaml", ".yml", ".txt", ".sh", ".bat")):
                fp = Path(root) / f
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(text.splitlines(), 1):
                        if pattern.lower() in line.lower():
                            rel = str(fp.relative_to(ROOT_DIR))
                            results.append(f"{rel}:{i}  {line.strip()[:100]}")
                            count += 1
                            if count >= 100:
                                break
                except Exception:
                    pass
            if count >= 100:
                break
        if count >= 100:
            break
    if not results:
        return f"（未找到匹配 '{pattern}' 的内容）"
    return f"找到 {count} 处匹配 '{pattern}':\n" + "\n".join(results[:50])


def run_tests(params: dict) -> str:
    """运行测试套件，返回结果摘要。"""
    test_path = str(params.get("path", "tests/"))
    verbose = str(params.get("verbose", "false")).lower() == "true"
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "-x"],
            capture_output=True, text=True, timeout=60,
            cwd=str(ROOT_DIR), encoding="utf-8", errors="replace",
        )
        out = r.stdout
        err = (r.stderr or "")[:500]
        # 解析结果
        passed = out.count(" PASSED")
        failed = out.count(" FAILED")
        errors = out.count(" ERROR")
        skipped = out.count(" SKIPPED")
        summary = f"测试完成：通过 {passed}，失败 {failed}，错误 {errors}，跳过 {skipped}"
        if failed or errors:
            summary += f"\n\n{out[-2000:]}"
        elif verbose:
            summary += f"\n\n{out[-1000:]}"
        return summary[:3000]
    except subprocess.TimeoutExpired:
        return "[run_tests 错误] 执行超时（>60s）"
    except Exception as e:
        return f"[run_tests 错误] {e}"


def gen_report(params: dict) -> str:
    """生成办公报告（会议纪要/周报/需求文档）。"""
    report_type = str(params.get("type", "meeting"))
    title = str(params.get("title", "未命名报告"))
    content = str(params.get("content", ""))
    output_path = str(params.get("output_path", ""))

    templates = {
        "meeting": f"""# 会议纪要

**标题：** {title}
**日期：** {time.strftime("%Y-%m-%d %H:%M")}
**参会人：** （待填写）

---

## 议题

{content or "（暂无议题）"}

---

## 决议事项

1. （待补充）

---

## 待办任务

| 任务 | 负责人 | 截止日期 | 状态 |
|------|--------|----------|------|
| | | | 待分配 |

---

*自动生成于 BlueDeer 办公系统*
""",
        "weekly": f"""# 周报

**姓名：** （待填写）
**周期：** {time.strftime("%Y-%m-%d")} ~ {time.strftime("%Y-%m-%d")}
**部门：** （待填写）

---

## 本周工作

{content or "（暂无内容）"}

---

## 下周计划

1.

---

## 风险与阻塞

（暂无）

---

*自动生成于 BlueDeer 办公系统*
""",
        "prd": f"""# 产品需求文档（PRD）

**文档名称：** {title}
**版本：** v1.0
**日期：** {time.strftime("%Y-%m-%d")}
**作者：** （待填写）

---

## 1. 背景与目标

{content or "（暂无内容）"}

## 2. 需求范围

### 2.1 包含
-

### 2.2 不包含
-

## 3. 功能需求

| 编号 | 功能 | 优先级 | 说明 |
|------|------|--------|------|
| FR-001 | | P0 | |

## 4. 非功能需求

- 性能：
- 安全：
- 兼容性：

---

*自动生成于 BlueDeer 办公系统*
""",
    }

    template = templates.get(report_type, templates["meeting"])
    doc = template

    if output_path:
        full = ROOT_DIR / output_path
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(doc, encoding="utf-8")
            return f"✅ 报告已生成：{output_path}（{len(doc)} 字符）"
        except Exception as e:
            return f"[gen_report 错误] 写入失败：{e}"
    return doc[:4000]


def git_status(params: dict) -> str:
    """Git 状态：查看分支、变更、日志。"""
    action = str(params.get("action", "status"))
    try:
        if action == "status":
            r = subprocess.run(["git", "status", "--short", "--branch"], capture_output=True,
                              text=True, timeout=10, cwd=str(ROOT_DIR), encoding="utf-8", errors="replace")
            return r.stdout[:2000] or "（工作区干净）"
        elif action == "branches":
            r = subprocess.run(["git", "branch", "-a"], capture_output=True,
                              text=True, timeout=10, cwd=str(ROOT_DIR), encoding="utf-8", errors="replace")
            return r.stdout[:2000]
        elif action == "log":
            n = int(params.get("n", 20))
            r = subprocess.run(["git", "log", f"-n{n}", "--oneline", "--decorate"], capture_output=True,
                              text=True, timeout=10, cwd=str(ROOT_DIR), encoding="utf-8", errors="replace")
            return r.stdout[:2000]
        elif action == "diff":
            r = subprocess.run(["git", "diff", "--stat"], capture_output=True,
                              text=True, timeout=10, cwd=str(ROOT_DIR), encoding="utf-8", errors="replace")
            return r.stdout[:2000] or "（无变更）"
        else:
            return f"[git_status 错误] 未知 action: {action}"
    except Exception as e:
        return f"[git_status 错误] {e}"


def run_command(params: dict) -> str:
    """执行 shell 命令（沙箱限制，仅允许安全命令）。"""
    cmd = str(params.get("command", ""))
    if not cmd:
        return "[run_command 错误] 缺少 command"
    # 安全检查：禁止危险命令
    dangerous = ["rm -rf /", "mkfs", "dd if=", "sudo ", "sudo:", "chmod 777", ":() {", "| wget", "; wget",
                 "curl |", "format(", "rm -rf /", "mv /", "cp /root", "sh -c", "bash -c"]
    for d in dangerous:
        if d.lower() in cmd.lower():
            return f"[run_command 错误] 命令被拦截：包含危险操作 '{d}'"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          timeout=30, cwd=str(ROOT_DIR), encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        result = out
        if r.returncode != 0:
            result = f"[退出码 {r.returncode}] {out}\n{err}".strip()
        elif err and "warning" not in err.lower():
            result = f"{out}\n[stderr] {err}"
        return (result or "（无输出）")[:3000]
    except subprocess.TimeoutExpired:
        return "[run_command 错误] 执行超时（>30s）"
    except Exception as e:
        return f"[run_command 错误] {e}"


def count_lines(params: dict) -> str:
    """统计代码行数。"""
    path = str(params.get("path", "."))
    full = (ROOT_DIR / path).resolve()
    if not full.startswith(str(ROOT_DIR)):
        return "[count_lines 错误] 路径越界"
    total = 0
    by_ext = {}
    for root, dirs, files in __import__("os").walk(full):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != ".venv"]
        for f in files:
            ext = Path(f).suffix.lower() or "(no ext)"
            fp = Path(root) / f
            try:
                count = sum(1 for _ in fp.open(encoding="utf-8", errors="ignore"))
                total += count
                by_ext[ext] = by_ext.get(ext, 0) + count
            except Exception:
                pass
    summary = f"总计 {total} 行\n"
    for ext, cnt in sorted(by_ext.items(), key=lambda x: -x[1]):
        summary += f"  {ext}: {cnt} 行\n"
    return summary


def diff_files(params: dict) -> str:
    """对比两个文件的差异（简化版 unified diff）。"""
    path1 = str(params.get("path1", ""))
    path2 = str(params.get("path2", ""))
    if not path1 or not path2:
        return "[diff_files 错误] 缺少 path1 或 path2"
    full1 = ROOT_DIR / path1
    full2 = ROOT_DIR / path2
    if not full1.startswith(str(ROOT_DIR)) or not full2.startswith(str(ROOT_DIR)):
        return "[diff_files 错误] 路径越界"
    try:
        t1 = full1.read_text(encoding="utf-8", errors="ignore").splitlines()
        t2 = full2.read_text(encoding="utf-8", errors="ignore").splitlines()
        # 简化 diff
        lines = []
        max_len = max(len(t1), len(t2))
        for i in range(min(max_len, 50)):  # 只显示前50行差异
            l1 = t1[i] if i < len(t1) else ""
            l2 = t2[i] if i < len(t2) else ""
            if l1 != l2:
                lines.append(f"-L{i+1}: {l1[:80]}")
                lines.append(f"+L{i+1}: {l2[:80]}")
        if not lines:
            return f"✅ {path1} 和 {path2} 内容相同"
        return f"📋 {path1} vs {path2} 差异（前50行）:\n" + "\n".join(lines)
    except Exception as e:
        return f"[diff_files 错误] {e}"


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
    # === 办公重型工具 ===
    Tool(
        "code_review",
        "代码审查：对指定 Python/JS/TS 文件做静态分析，找出 bug、规范问题、性能隐患、安全漏洞",
        '{"path": "web_server/app.py"}',
        code_review,
    ),
    Tool(
        "search_code",
        "全局搜索：在项目内 grep 匹配文本（支持 .py .js .ts .html .css .md 等）",
        '{"pattern": "class Agent", "path_filter": "core/"}',
        search_code,
    ),
    Tool(
        "run_tests",
        "运行 pytest 测试套件，返回通过/失败/错误摘要",
        '{"path": "tests/", "verbose": true}',
        run_tests,
    ),
    Tool(
        "gen_report",
        "生成办公报告：会议纪要/周报/需求文档（PRD），可保存到文件",
        '{"type": "meeting", "title": "周会", "content": "讨论Agent架构", "output_path": "docs/meeting_2026.md"}',
        gen_report,
    ),
    Tool(
        "git_status",
        "查看 Git 状态：工作区变更、分支、提交历史",
        '{"action": "status"}',
        git_status,
    ),
    Tool(
        "run_command",
        "执行 shell 命令（沙箱限制，禁止危险操作）",
        '{"command": "python -m py_compile web_server/app.py"}',
        run_command,
    ),
    Tool(
        "count_lines",
        "统计代码行数（按文件类型分类）",
        '{"path": "core/"}',
        count_lines,
    ),
    Tool(
        "diff_files",
        "对比两个文件的差异",
        '{"path1": "old.py", "path2": "new.py"}',
        diff_files,
    ),
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
