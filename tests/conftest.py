"""pytest 全局基建：sys.path + 数据隔离。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_data(tmp_path, monkeypatch):
    """把 onboarding 等硬编码 data/ 的模块重定向到临时目录。

    用法: def test_x(isolated_data): ...
    对 onboarding：patch 模块级 _ONBOARDING_PATH + 重置单例。
    """
    import core.digital_life.onboarding as ob

    monkeypatch.setattr(ob, "_ONBOARDING_PATH", str(tmp_path / "onboarding.json"))
    ob.OnboardingManager._instance = None
    return tmp_path
