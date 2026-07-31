"""BlueDeer 统一配置中心：热重载 + 环境变量覆盖。

用法：
    cfg = get_config()
    cfg.reload()  # 从文件/env 热重载
    val = cfg.get("model.default_model", "Doubao-Seed-2.1-Pro")
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Environment(Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    TEST = "test"


class ResponseStyle(Enum):
    DEFAULT = "default"
    FORMAL = "formal"
    CASUAL = "casual"
    TECHNICAL = "technical"
    CREATIVE = "creative"


@dataclass(slots=True)
class ModelConfig:
    default_model: str = "Doubao-Seed-2.1-Pro"
    task_model_map: dict[str, str] = field(default_factory=lambda: {
        "code": "Doubao-Seed-Code",
        "architecture": "Doubao-Seed-2.1-Pro",
        "batch": "Doubao-Seed-2.1-Turbo",
        "voice": "MiniMax-M3",
        "reasoning": "Doubao-Seed-2.1-Pro",
        "multimedia": "Doubao-Vision-Pro",
    })
    task_fallbacks: dict[str, list[str]] = field(default_factory=lambda: {
        "code": ["Doubao-Seed-2.1-Pro", "Doubao-Seed-2.1-Turbo"],
        "architecture": ["Doubao-Seed-2.1-Turbo", "Doubao-Seed-Code"],
        "batch": ["Doubao-Seed-2.1-Turbo"],
        "voice": ["Doubao-Seed-2.1-Turbo"],
        "reasoning": ["Doubao-Seed-Code", "Doubao-Seed-2.1-Turbo"],
        "multimedia": ["Doubao-Seed-2.1-Pro"],
    })
    fail_threshold: int = 3
    degrade_ttl_seconds: float = 30.0
    lowcost_models: set[str] = field(default_factory=lambda: {
        "Doubao-Seed-2.1-Turbo", "MiniMax-M3",
    })
    baseline_model: str = "Doubao-Seed-2.1-Pro"
    baseline_multiplier: float = 1.5


@dataclass(slots=True)
class RewardConfig:
    coins_success: int = 10
    coins_failed: int = -8
    exp_success: int = 20
    exp_failed: int = 2
    favor_base_gain: int = 5
    favor_base_loss: int = 5
    favor_init: int = 50
    favor_min: int = 0
    favor_decay_k: int = 200
    consecutive_fail_penalty: int = 2
    consecutive_fail_cap: int = 20
    token_threshold: int = 10000
    token_overspend_penalty: int = 1


@dataclass(slots=True)
class DreamConfig:
    nightmare_threshold: int = 3
    memory_archive_ttl: float = 30 * 24 * 3600
    fragile_min_len: int = 20
    quality_high_code_lines: int = 20
    quality_high_token: int = 500
    quality_legendary_code_lines: int = 100
    quality_legendary_token: int = 200


@dataclass(slots=True)
class TaskConfig:
    timeout_seconds: float = 120.0
    max_reallocate: int = 2
    default_wait_timeout: float = 30.0
    agent_max_in_flight: int = 3
    retry_enabled: bool = True
    retry_max_attempts: int = 3
    retry_base_delay: float = 2.0
    retry_max_delay: float = 120.0
    retry_jitter: bool = True


@dataclass(slots=True)
class ToolConfig:
    max_retries: int = 3
    circuit_threshold: int = 5


@dataclass(slots=True)
class SchedulerConfig:
    enabled: bool = False
    tick_seconds: float = 60.0


@dataclass(slots=True)
class WebhookConfig:
    enabled: bool = False
    default_timeout_seconds: float = 10.0
    default_max_retries: int = 3


@dataclass(slots=True)
class AlertConfig:
    enabled: bool = True
    default_rules: list[dict] = field(default_factory=lambda: [
        {"id": "task-failure-rate", "name": "任务失败率过高", "metric": "failed_rate",
         "operator": "gt", "threshold": 0.3, "severity": "warning",
         "cooldown_sec": 300,
         "message_template": "任务失败率 {value:.0%} > {threshold:.0%}"},
        {"id": "task-pending-surge", "name": "待处理任务堆积", "metric": "pending_count",
         "operator": "gt", "threshold": 50, "severity": "warning", "cooldown_sec": 600},
        {"id": "batch-fail-spike", "name": "批量失败激增", "metric": "failed_delta",
         "operator": "gt", "threshold": 20, "severity": "critical", "cooldown_sec": 300},
    ])


@dataclass(slots=True)
class LogConfig:
    log_dir: str = "logs"
    trace_log_file: str = "trace.log"
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass(slots=True)
class AppConfig:
    environment: Environment = Environment.LOCAL
    model: ModelConfig = field(default_factory=ModelConfig)
    reward: RewardConfig = field(default_factory=RewardConfig)
    dream: DreamConfig = field(default_factory=DreamConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    tool: ToolConfig = field(default_factory=ToolConfig)
    log: LogConfig = field(default_factory=LogConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    db_root: str = "vector_db/data"
    use_real_api: bool = False
    config_file: str = ""

    _file_mtime: float = 0.0

    def _set(self, section: str, key: str, value: Any) -> None:
        obj = getattr(self, section, None)
        if obj and hasattr(obj, key):
            setattr(obj, key, value)

    def get(self, path: str, default: Any = None) -> Any:
        parts = path.split(".")
        obj = self
        for p in parts:
            if hasattr(obj, p):
                obj = getattr(obj, p)
            else:
                return default
        return obj

    def apply_env(self) -> None:
        mapping = {
            "BLUEDEER_ENV": ("environment", Environment),
            "DOUBAO_API_KEY": ("use_real_api", lambda v: bool(v)),
            "LOG_LEVEL": ("log", "level"),
            "LOG_DIR": ("log", "log_dir"),
            "TASK_TIMEOUT_SECONDS": ("task", "timeout_seconds"),
            "MODEL_FAIL_THRESHOLD": ("model", "fail_threshold"),
            "SCHEDULER_ENABLED": ("scheduler", "enabled"),
            "WEBHOOK_ENABLED": ("webhook", "enabled"),
            "DB_ROOT": ("db_root", None),
        }
        for env_key, cfg_path in mapping.items():
            val = os.environ.get(env_key)
            if val is None:
                continue
            if isinstance(cfg_path[1], type) and issubclass(cfg_path[1], Enum):
                self._set("", cfg_path[0], cfg_path[1](val))
            elif cfg_path[1] is None:
                setattr(self, cfg_path[0], val)
            else:
                section, attr = cfg_path
                cast = type(getattr(getattr(self, section), attr))
                try:
                    self._set(section, attr, cast(val))
                except (ValueError, TypeError):
                    pass

    @classmethod
    def from_env(cls) -> AppConfig:
        cfg = cls()
        cfg.apply_env()
        return cfg

    @classmethod
    def from_file(cls, path: str) -> AppConfig:
        cfg = cls()
        cfg.config_file = path
        raw: dict[str, Any] = {}
        if path.endswith((".yaml", ".yml")):
            try:
                import yaml
            except ImportError:
                pass
            else:
                with open(path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
        elif path.endswith(".toml"):
            import tomllib
            with open(path, "rb") as f:
                raw = tomllib.load(f)
        for section, section_cfg in raw.items():
            if isinstance(section_cfg, dict):
                for k, v in section_cfg.items():
                    cfg._set(section, k, v)
        cfg.apply_env()
        try:
            cfg._file_mtime = os.path.getmtime(path)
        except OSError:
            pass
        errors = cfg.validate()
        if errors:
            import logging
            logging.getLogger("bluedeer.config").warning(
                "配置验证发现 %d 个问题: %s", len(errors), errors
            )
        return cfg

    def reload(self) -> bool:
        if not self.config_file:
            self.apply_env()
            return True
        try:
            new_mtime = os.path.getmtime(self.config_file)
            if new_mtime <= self._file_mtime:
                self.apply_env()
                return False
        except OSError:
            return False
        new_cfg = AppConfig.from_file(self.config_file)
        for section_name in ("model", "reward", "dream", "task", "tool",
                              "log", "scheduler", "webhook", "alerts"):
            src = getattr(new_cfg, section_name)
            dst = getattr(self, section_name)
            for k, v in src.__dict__.items():
                setattr(dst, k, v)
        self.db_root = new_cfg.db_root
        self.use_real_api = new_cfg.use_real_api
        self._file_mtime = new_mtime
        self.apply_env()
        return True

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.task.timeout_seconds <= 0:
            errors.append("task.timeout_seconds 必须 > 0")
        if self.model.fail_threshold < 1:
            errors.append("model.fail_threshold 必须 ≥ 1")
        if self.tool.max_retries < 0:
            errors.append("tool.max_retries 不能为负")
        if self.tool.circuit_threshold < 1:
            errors.append("tool.circuit_threshold 必须 ≥ 1")
        return errors


_config: AppConfig | None = None
_config_file: str = ""


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig.from_env()
        if _config_file:
            _config = AppConfig.from_file(_config_file)
        errors = _config.validate()
        if errors:
            import logging
            logging.getLogger("bluedeer.config").warning(
                "配置验证发现 %d 个问题: %s", len(errors), errors
            )
    return _config


def set_config(cfg: AppConfig) -> None:
    global _config
    _config = cfg


def set_config_file(path: str) -> None:
    global _config_file, _config
    _config_file = path
    _config = AppConfig.from_file(path)