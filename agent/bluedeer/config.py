"""加载 config.json，密钥一律走环境变量，不落配置文件。"""

import json
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = {
    "agent_name": "BlueDeer",
    "provider": "mock",
    "ollama_model": "qwen2.5vl:7b",
    "ollama_base_url": "http://localhost:11434",
    "api_base": "",
    "api_model": "",
    "api_key": "",
    "trace": True,
    "runs_dir": "runs",
    "role": "",
    "roles_dir": "roles",
    "system_prompt": "",
    "server_host": "127.0.0.1",
    "server_port": 8000,
    "default_auto_reply_template": "收到，{from}。任务「{task}」已受理，正在处理…",
    "agent_loop": True,
    "max_steps": 8,
    "tools_enabled": [],
    "memory_file": "data/agent_memory.jsonl",
    "memory_turns": 4,
    "log_level": "INFO",
    "layers": {},
}


def load_config(path: Path | None = None) -> dict:
    path = path or ROOT_DIR / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        cfg.update(data)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    """只落盘与默认值不同的键，保持 config.json 干净。"""
    path = path or ROOT_DIR / "config.json"
    data = {k: v for k, v in cfg.items() if k not in DEFAULT_CONFIG or DEFAULT_CONFIG[k] != v}
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def resolve_path(cfg: dict, key: str) -> Path:
    """把相对路径解析为相对项目根的绝对路径。"""
    p = Path(cfg.get(key) or "")
    if not p.is_absolute():
        p = ROOT_DIR / p
    return p


def get_env(key: str, default: str = "") -> str:
    """读取环境变量，密钥只从这里取。"""
    return os.environ.get(key, default)
