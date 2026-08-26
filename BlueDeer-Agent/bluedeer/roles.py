"""角色卡：从 markdown 文件加载角色系统提示词（复用老版动物角色资产）。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Role:
    name: str
    system_prompt: str
    title: str = ""


def list_roles(roles_dir) -> list[str]:
    d = Path(roles_dir)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.md"))


def load_role(roles_dir, name: str) -> Role | None:
    path = Path(roles_dir) / f"{name}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    title = name
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return Role(name=name, system_prompt=text, title=title)


def resolve_system_prompt(config: dict) -> str | None:
    """优先级：role 文件 > 内联 system_prompt > 无。"""
    role_name = config.get("role") or ""
    roles_dir = config.get("roles_dir") or ""
    if role_name and roles_dir:
        role = load_role(roles_dir, role_name)
        if role:
            return role.system_prompt
    inline = config.get("system_prompt") or ""
    return inline or None
