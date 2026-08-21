"""SQLiteStateStore TTL 清理单测。"""

from __future__ import annotations

import asyncio

import pytest

from core.state_store import SQLiteStateStore


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "test.db"
    return SQLiteStateStore(str(db))


@pytest.mark.asyncio
async def test_cleanup_old_records(store: SQLiteStateStore) -> None:
    await store.save("key-1", {"value": "old"})
    await asyncio.sleep(0.1)
    await store.save("key-2", {"value": "new"})
    deleted = await store.cleanup(older_than=0.05)
    assert deleted >= 1
    assert await store.load("key-1") is None
    assert await store.load("key-2") is not None


@pytest.mark.asyncio
async def test_list_keys(store: SQLiteStateStore) -> None:
    await store.save("a:1", {"v": 1})
    await store.save("a:2", {"v": 2})
    keys = await store.list_keys("a:")
    assert "a:1" in keys
    assert "a:2" in keys
