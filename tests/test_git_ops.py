"""Tests for core.git_ops module."""

from __future__ import annotations

from core.git_ops import GitHubClient, GitOps, GitStatus


class TestGitOps:
    def test_is_repo(self, tmp_path):
        ops = GitOps(str(tmp_path))
        assert ops.is_repo() is False

    def test_current_branch_not_repo(self, tmp_path):
        ops = GitOps(str(tmp_path))
        assert ops.current_branch() == ""

    def test_status_empty(self, tmp_path):
        ops = GitOps(str(tmp_path))
        status = ops.status()
        assert isinstance(status, GitStatus)
        assert status.has_changes is False

    def test_forbidden_filter(self):
        ops = GitOps(".")
        assert ops._is_forbidden(".env") is True
        assert ops._is_forbidden("README.md") is False


class TestGitHubClient:
    def test_no_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client = GitHubClient()
        assert client.has_token is False
        ok, resp = client.list_prs("owner/repo")
        assert ok is True
        assert resp[0].get("mock") is True

    def test_create_pr_no_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client = GitHubClient()
        ok, resp = client.create_pr("owner/repo", "Title", "main", "dev")
        assert ok is True
        assert resp.get("mock") is True
