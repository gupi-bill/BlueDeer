"""006-31: YAML 配置 schema 校验（未知项/类型强转/枚举/范围）。"""

from __future__ import annotations

from pathlib import Path

from core.config import AppConfig, Environment


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_unknown_section_reported(tmp_path):
    p = _write_yaml(tmp_path, "nope_section:\n  a: 1\n")
    cfg = AppConfig.from_file(str(p))
    assert any("nope_section" in e for e in cfg._load_errors)


def test_unknown_field_reported(tmp_path):
    p = _write_yaml(tmp_path, "model:\n  not_a_field: 1\n")
    cfg = AppConfig.from_file(str(p))
    assert any("model.not_a_field" in e for e in cfg._load_errors)


def test_top_level_str_coerced(tmp_path):
    p = _write_yaml(tmp_path, "db_root: /data/bluedeer\n")
    cfg = AppConfig.from_file(str(p))
    assert cfg.db_root == "/data/bluedeer"


def test_top_level_enum(tmp_path):
    p = _write_yaml(tmp_path, "environment: cloud\n")
    cfg = AppConfig.from_file(str(p))
    assert cfg.environment == Environment.CLOUD


def test_top_level_bool_coerced(tmp_path):
    p = _write_yaml(tmp_path, "use_real_api: true\n")
    cfg = AppConfig.from_file(str(p))
    assert cfg.use_real_api is True


def test_int_coerced_from_str(tmp_path):
    p = _write_yaml(tmp_path, 'model:\n  fail_threshold: "7"\n')
    cfg = AppConfig.from_file(str(p))
    assert cfg.model.fail_threshold == 7


def test_float_coerced(tmp_path):
    p = _write_yaml(tmp_path, "task:\n  timeout_seconds: 42.5\n")
    cfg = AppConfig.from_file(str(p))
    assert cfg.task.timeout_seconds == 42.5


def test_bool_coerced_from_str(tmp_path):
    p = _write_yaml(tmp_path, 'task:\n  retry_enabled: "false"\n')
    cfg = AppConfig.from_file(str(p))
    assert cfg.task.retry_enabled is False


def test_lowcost_models_list_to_set(tmp_path):
    p = _write_yaml(tmp_path, "model:\n  lowcost_models: [A, B]\n")
    cfg = AppConfig.from_file(str(p))
    assert cfg.model.lowcost_models == {"A", "B"}


def test_bad_type_reported(tmp_path):
    p = _write_yaml(tmp_path, "model:\n  fail_threshold: [1, 2]\n")
    cfg = AppConfig.from_file(str(p))
    assert any("model.fail_threshold" in e for e in cfg._load_errors)


def test_bad_log_level_reported(tmp_path):
    p = _write_yaml(tmp_path, "log:\n  level: VERBOSE\n")
    cfg = AppConfig.from_file(str(p))
    assert any("log.level" in e for e in cfg._load_errors)


def test_negative_value_reported(tmp_path):
    p = _write_yaml(tmp_path, "model:\n  fail_threshold: -3\n")
    cfg = AppConfig.from_file(str(p))
    assert any("model.fail_threshold" in e for e in cfg.validate())


def test_valid_config_no_errors(tmp_path):
    p = _write_yaml(
        tmp_path,
        "environment: test\n"
        "db_root: data/x\n"
        "model:\n  default_model: M1\n  fail_threshold: 3\n"
        "task:\n  timeout_seconds: 60\n"
        "log:\n  level: debug\n",
    )
    cfg = AppConfig.from_file(str(p))
    assert cfg._load_errors == []
    assert cfg.log.level.upper() == "DEBUG"
    assert cfg.environment == Environment.TEST
    assert cfg.db_root == "data/x"


def test_validate_rejects_log_level_direct():
    cfg = AppConfig()
    cfg.log.level = "NOPE"
    assert any("log.level" in e for e in cfg.validate())


def test_non_numeric_sections_skipped():
    cfg = AppConfig()
    cfg.log.level = "debug"
    cfg.reward.favor_base_gain = -1
    errors = cfg.validate()
    assert any("reward.favor_base_gain" in e for e in errors)
