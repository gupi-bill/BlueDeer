"""BlueDeer 任务模板引擎：可复用任务模板的注册、渲染、执行。

用法：
    tmpl = TaskTemplates()
    tmpl.register(TaskTemplate(id="code-review", type="code", prompt="审查代码…", assignee="squirrel"))
    task = tmpl.render("code-review", target_file="src/main.py")
    await harness.submit_task(task)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from core.task import Task

logger = logging.getLogger("bluedeer.task_templates")

_TEMPLATE_FILE = "data/task_templates.json"


@dataclass(slots=True)
class TaskTemplate:
    """任务模板定义。"""

    id: str
    type: str = "general"
    prompt_template: str = ""
    assignee: str = ""
    default_payload: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    timeout_seconds: float = 0.0
    version: int = 1
    version_history: list[dict[str, Any]] = field(default_factory=list)


class TaskTemplates:
    """任务模板引擎。"""

    def __init__(self) -> None:
        self._templates: dict[str, TaskTemplate] = {}
        self._load()

    # ---- 注册/注销 ----

    def register(self, template: TaskTemplate) -> str:
        existing = self._templates.get(template.id)
        if existing is not None:
            self._bump_version(template.id)
            template.version = existing.version
            template.version_history = list(existing.version_history)
        self._templates[template.id] = template
        self._save()
        logger.info("任务模板已注册: %s (%s)", template.id, template.type)
        return template.id

    def unregister(self, template_id: str) -> bool:
        ok = self._templates.pop(template_id, None) is not None
        if ok:
            self._save()
        return ok

    def get(self, template_id: str) -> TaskTemplate | None:
        return self._templates.get(template_id)

    def list_templates(self, tag: str = "") -> list[TaskTemplate]:
        if tag:
            return [t for t in self._templates.values() if tag in t.tags]
        return list(self._templates.values())

    # ---- 渲染 ----

    def render(
        self,
        template_id: str,
        **variables: Any,
    ) -> Task:
        """渲染模板为 Task。

        Args:
            template_id: 模板 ID。
            **variables: 模板变量，会替换 prompt_template 中的 {key} 占位符。

        Returns:
            Task 实例。
        """
        tmpl = self._templates.get(template_id)
        if tmpl is None:
            raise KeyError(f"模板 {template_id} 未注册")

        prompt = tmpl.prompt_template
        for k, v in variables.items():
            placeholder = "{" + k + "}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(v))

        payload = dict(tmpl.default_payload)
        payload["prompt"] = prompt
        payload.update(variables)

        return Task(
            type=tmpl.type,
            payload=payload,
            assignee=tmpl.assignee,
        )

    def render_template(
        self,
        template_name: str,
        **variables: Any,
    ) -> Task:
        """渲染模板（双花括号 {{var}} 占位符风格）。

        Args:
            template_name: 模板 ID。
            **variables: 模板变量，会替换 prompt_template 中的 {{var}} 占位符。

        Returns:
            Task 实例。
        """
        tmpl = self._templates.get(template_name)
        if tmpl is None:
            raise KeyError(f"模板 {template_name} 未注册")

        prompt = tmpl.prompt_template
        for k, v in variables.items():
            placeholder = "{{" + k + "}}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(v))

        payload = dict(tmpl.default_payload)
        payload["prompt"] = prompt
        payload.update(variables)

        return Task(
            type=tmpl.type,
            payload=payload,
            assignee=tmpl.assignee,
        )

    def list_versions(self, template_name: str) -> list[dict[str, Any]]:
        """查看模板的版本历史。

        Args:
            template_name: 模板 ID。

        Returns:
            版本历史列表，按版本号降序。
        """
        tmpl = self._templates.get(template_name)
        if tmpl is None:
            raise KeyError(f"模板 {template_name} 未注册")
        history = list(tmpl.version_history)
        history.append(
            {
                "version": tmpl.version,
                "prompt_template": tmpl.prompt_template,
                "updated_at": __import__("datetime").datetime.now().isoformat(),
            }
        )
        history.sort(key=lambda h: h["version"], reverse=True)
        return history

    def _bump_version(self, template_id: str) -> None:
        tmpl = self._templates.get(template_id)
        if tmpl is None:
            return
        tmpl.version_history.append(
            {
                "version": tmpl.version,
                "prompt_template": tmpl.prompt_template,
                "updated_at": __import__("datetime").datetime.now().isoformat(),
            }
        )
        tmpl.version += 1

    # ---- 内置模板 ----

    def register_builtins(self) -> None:
        """注册一组内置模板。"""
        builtins = [
            TaskTemplate(
                id="code-review",
                type="code",
                prompt_template="请审查以下 {language} 代码，检查潜在 Bug、安全问题和性能优化点：\n\n```{language}\n{code}\n```",
                assignee="squirrel",
                tags=["code", "review"],
                description="代码审查",
            ),
            TaskTemplate(
                id="security-scan",
                type="code",
                prompt_template="扫描以下内容的安全风险（SQL 注入、XSS、路径遍历、密钥泄露）：\n\n{content}",
                assignee="hedgehog",
                tags=["security", "scan"],
                description="安全扫描",
            ),
            TaskTemplate(
                id="unit-test",
                type="code",
                prompt_template="为以下 {language} 代码编写单元测试，覆盖正常路径和边界情况：\n\n```{language}\n{code}\n```",
                assignee="fox",
                tags=["test", "code"],
                description="生成单元测试",
            ),
            TaskTemplate(
                id="refactor",
                type="code",
                prompt_template="重构以下 {language} 代码，提高可读性和可维护性：\n\n```{language}\n{code}\n```",
                assignee="squirrel",
                tags=["code", "refactor"],
                description="代码重构",
            ),
            TaskTemplate(
                id="deploy-check",
                type="batch",
                prompt_template="检查以下部署清单：\n\n{checklist}",
                assignee="beaver",
                tags=["ops", "deploy"],
                description="部署检查",
            ),
            TaskTemplate(
                id="daily-report",
                type="general",
                prompt_template="生成以下项目的日报：\n\n项目：{project}\n日期：{date}\n进度：{progress}",
                assignee="owl",
                tags=["report", "daily"],
                description="日报生成",
            ),
            TaskTemplate(
                id="dream-review",
                type="general",
                prompt_template="回顾以下梦境记录并提取洞察：\n\n{dream_content}",
                assignee="owl",
                tags=["dream", "review"],
                description="梦境回顾",
            ),
        ]
        for t in builtins:
            self.register(t)

    # ---- 持久化 ----

    def _load(self) -> None:
        try:
            from core.database import Database

            rows = Database().load_task_templates()
            for item in rows:
                tmpl = TaskTemplate(**item)
                self._templates[tmpl.id] = tmpl
        except Exception as e:
            logger.warning("从数据库加载任务模板失败: %s", e)

    def _save(self) -> None:
        try:
            raw = {tid: asdict(t) for tid, t in self._templates.items()}
            from core.database import Database

            Database().save_task_templates(raw)
        except Exception as e:
            logger.warning("保存任务模板到数据库失败: %s", e)
