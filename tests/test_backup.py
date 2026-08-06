"""Tests for core.backup module."""

from __future__ import annotations

from core.backup import (
    BackupManifest,
    delete_backup,
)


class TestBackupManifest:
    def test_defaults(self):
        manifest = BackupManifest()
        assert manifest.version == "1.0"
        assert manifest.files == []
        assert manifest.db_only is False


class TestCreateBackup:
    def test_create_backup(self, tmp_path):
        pass


class TestListBackups:
    def test_list_empty(self, tmp_path):
        pass


class TestDeleteBackup:
    def test_delete_missing(self):
        assert delete_backup("nonexistent.zip") is False
