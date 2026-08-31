# -*- coding: utf-8 -*-
"""办公工作空间 API：代码编辑、Agent 协作、任务执行。"""

import json
import logging
import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("bluedeer.workspace")

router = APIRouter(prefix="/workspace")

# 工作空间根目录（可配置）
_WORKSPACE_ENV = os.environ.get("BLUEDEER_WORKSPACE_DIR")
if _WORKSPACE_ENV:
    WORKSPACE_DIR = _WORKSPACE_ENV
else:
    # 相对于 routes_workspace.py 的位置: web_server/ 上一级是 BlueDeer/
    _ws = (Path(__file__).resolve().parent.parent / "workspace").resolve()
    WORKSPACE_DIR = str(_ws)


def _safe_path(rel: str) -> Path | None:
    """验证路径在 workspace 内。"""
    if not rel:
        rel = "."
    p = (Path(WORKSPACE_DIR) / rel).resolve()
    root = Path(WORKSPACE_DIR).resolve()
    if not str(p).startswith(str(root)):
        return None
    return p


@router.get("/files/list", summary="列出工作空间文件")
async def ws_files_list(path: str = ""):
    p = _safe_path(path or ".")
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    if not p.exists():
        return JSONResponse({"error": "目录不存在"}, status_code=404)
    items = []
    for child in sorted(p.iterdir()):
        try:
            stat = child.stat()
            items.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if child.is_file() else 0,
                "modified": stat.st_mtime,
            })
        except Exception:
            pass
    return {"path": path, "items": items}


@router.get("/files/read", summary="读取文件")
async def ws_files_read(path: str = ""):
    p = _safe_path(path)
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    if not p.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    try:
        text = p.read_text(encoding="utf-8")
        return {"path": str(path), "content": text, "lines": len(text.splitlines())}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/files/write", summary="写入文件")
async def ws_files_write(request: Request):
    body = await request.json() if request.body else {}
    path = body.get("path", "")
    content = body.get("content", "")
    p = _safe_path(path)
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": p.stat().st_size}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/files/create", summary="创建文件")
async def ws_files_create(request: Request):
    body = await request.json() if request.body else {}
    path = body.get("path", "")
    p = _safe_path(path)
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("", encoding="utf-8")
        return {"ok": True, "path": str(path)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/files/delete", summary="删除文件/目录")
async def ws_files_delete(request: Request):
    body = await request.json() if request.body else {}
    path = body.get("path", "")
    p = _safe_path(path)
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    try:
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"ok": True, "path": str(path)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/agent/run", summary="Agent 执行任务")
async def ws_agent_run(request: Request):
    """调用 Agent 执行一个任务，返回执行结果和步骤。"""
    body = await request.json() if request.body else {}
    task = body.get("task", "")
    role = body.get("role", "senior_dev")
    max_steps = int(body.get("max_steps", 10))

    if not task:
        return JSONResponse({"error": "task 不能为空"}, status_code=400)

    # 加载 agent 配置
    agent_dir = Path(__file__).parent.parent / "agent"
    config_path = agent_dir / "config.json"
    cfg = {}
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg["role"] = role
    cfg["max_steps"] = max_steps

    # 确保 agent 模块可导入
    sys.path.insert(0, str(agent_dir))
    try:
        from bluedeer.agent import BlueDeerAgent
        from bluedeer.config import load_config as _lc

        agent_cfg = _lc()
        agent_cfg.update(cfg)
        agent = BlueDeerAgent(agent_cfg)
        result = agent.run(task)

        return {
            "ok": True,
            "role": role,
            "task": task,
            "output": result,
            "ts": int(time.time()),
        }
    except Exception as e:
        logger.exception("Agent 执行失败")
        return JSONResponse({"error": f"Agent 执行失败: {e}"}, status_code=500)


@router.get("/agent/roles", summary="获取可用角色列表")
async def ws_agent_roles():
    """列出 agent/roles/ 目录下的所有角色。"""
    agent_dir = Path(__file__).parent.parent / "agent" / "roles"
    roles = []
    if agent_dir.exists():
        for f in sorted(agent_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            title = f.stem
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            roles.append({"id": f.stem, "name": title})
    return {"roles": roles}


@router.get("/agent/config", summary="获取 Agent 配置")
async def ws_agent_config():
    agent_dir = Path(__file__).parent.parent / "agent"
    config_path = agent_dir / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            # 脱敏：不返回 api_key
            cfg.pop("api_key", None)
            return {"config": cfg}
        except Exception:
            pass
    return {"config": {}}


@router.post("/agent/config", summary="更新 Agent 配置")
async def ws_agent_config_update(request: Request):
    agent_dir = Path(__file__).parent.parent / "agent"
    config_path = agent_dir / "config.json"
    body = await request.json() if request.body else {}
    try:
        existing = {}
        if config_path.exists():
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        existing.update(body)
        if body.get("api_key"):
            existing["api_key"] = body["api_key"]
        config_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== 文件上传 =====
@router.post("/files/upload", summary="上传文件到工作空间")
async def ws_files_upload(request: Request):
    body = await request.form() if request.body else {}
    path = str(body.get("path", ""))
    file_obj = body.get("file")
    if not file_obj or not path:
        return JSONResponse({"error": "缺少 path 或 file"}, status_code=400)
    p = _safe_path(path)
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        content = await file_obj.read()
        p.write_bytes(content)
        return {"ok": True, "path": str(path), "bytes": len(content)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== 文件下载 =====
@router.get("/files/download", summary="下载工作空间文件")
async def ws_files_download(path: str = ""):
    p = _safe_path(path)
    if p is None:
        return JSONResponse({"error": "路径越界"}, status_code=403)
    if not p.exists() or p.is_dir():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    from fastapi.responses import FileResponse
    return FileResponse(str(p), filename=p.name)


# ===== 项目模板 =====
PROJECT_TEMPLATES = {
    "fastapi": {
        "name": "FastAPI 项目",
        "files": {
            "main.py": '''"""FastAPI 项目入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MyApp", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Hello BlueDeer"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
''',
            "requirements.txt": "fastapi>=0.111.0\nuvicorn>=0.30.0\npydantic>=2.0.0\n",
            "README.md": "# MyApp\n\nFastAPI 项目，由 BlueDeer 生成\n\n启动：`python main.py`\n",
            "tests/test_main.py": '''"""基本测试"""
from main import app

def test_root():
    assert app is not None
''',
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\n",
        },
    },
    "flask": {
        "name": "Flask 项目",
        "files": {
            "app.py": '''"""Flask 项目入口"""
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def root():
    return jsonify({"message": "Hello BlueDeer"})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
''',
            "requirements.txt": "flask>=3.0.0\n",
            "README.md": "# MyApp\n\nFlask 项目，由 BlueDeer 生成\n\n启动：`python app.py`\n",
        },
    },
    "python_pkg": {
        "name": "Python 包结构",
        "files": {
            "src/myproject/__init__.py": '''"""MyProject"""
__version__ = "0.1.0"
''',
            "src/myproject/core.py": '''"""核心模块"""

def main():
    print("Hello BlueDeer!")
    return 0

if __name__ == "__main__":
    main()
''',
            "pyproject.toml": """[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.11"
""",
            "README.md": "# MyProject\n\nPython 包，由 BlueDeer 生成\n",
            "tests/test_core.py": '''"""测试核心模块"""
from myproject.core import main

def test_main():
    assert main() == 0
''',
        },
    },
    "script": {
        "name": "Python 脚本",
        "files": {
            "main.py": '''"""项目脚本入口"""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="项目脚本")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    if args.verbose:
        print(f"工作目录: {Path.cwd()}")
    print("Hello BlueDeer!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
            "README.md": "# 项目脚本\n\n用法：`python main.py [--verbose]`\n",
        },
    },
}


@router.get("/projects/templates", summary="获取项目模板列表")
async def ws_project_templates():
    return {
        "templates": [
            {"id": k, "name": v["name"]}
            for k, v in PROJECT_TEMPLATES.items()
        ]
    }


@router.post("/projects/init", summary="初始化项目")
async def ws_project_init(request: Request):
    body = await request.json() if request.body else {}
    template_id = str(body.get("template", "fastapi"))
    project_name = str(body.get("name", "my_project")).replace(" ", "_")
    output_path = str(body.get("path", f"code/{project_name}"))

    tpl = PROJECT_TEMPLATES.get(template_id)
    if not tpl:
        return JSONResponse({"error": f"未知模板: {template_id}"}, status_code=400)

    try:
        base = Path(WORKSPACE_DIR) / output_path
        base.mkdir(parents=True, exist_ok=True)
        for fname, content in tpl["files"].items():
            fp = base / fname
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "path": str(output_path),
            "name": tpl["name"],
            "files_created": list(tpl["files"].keys()),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== 会话历史 =====
import json as _json
from pathlib import Path as _Path

HISTORY_FILE = _Path(WORKSPACE_DIR).parent / "data" / "workspace_history.json"


@router.get("/session/history", summary="获取会话历史")
async def ws_session_history(limit: int = 20):
    try:
        if HISTORY_FILE.exists():
            data = _json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            return {"history": data[-limit:]}
    except Exception:
        pass
    return {"history": []}


@router.post("/session/history", summary="保存会话记录")
async def ws_session_save(request: Request):
    body = await request.json() if request.body else {}
    record = {
        "ts": int(_time()),
        "role": body.get("role", ""),
        "task": body.get("task", "")[:200],
        "output_len": len(body.get("output", "")),
        "ok": body.get("ok", False),
    }
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if HISTORY_FILE.exists():
            try:
                existing = _json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.append(record)
        HISTORY_FILE.write_text(_json.dumps(existing, ensure_ascii=False), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

import time as _time
