"""BlueDeer Git 自动化 + GitHub REST 客户端。

GitOps：subprocess 调 git，本地操作。
GitHubClient：urllib + REST API，需 GITHUB_TOKEN 环境变量。

安全约束：
- 不自动 push --force
- 不提交 .env / credentials / secrets
- commit message 用 HEREDOC 避免转义
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.security import sanitize_log

logger = logging.getLogger("bluedeer.gitops")

# 禁止提交的文件模式（安全黑名单）
_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    ".env",
    "credentials",
    "secret",
    "token",
    "apikey",
    "private_key",
    "__pycache__",
    ".pyc",
    ".log",
)


@dataclass
class GitStatus:
    """Git 状态快照。"""

    branch: str = ""
    changed: list[str] = None  # type: ignore
    staged: list[str] = None  # type: ignore
    untracked: list[str] = None  # type: ignore
    has_changes: bool = False

    def __post_init__(self) -> None:
        if self.changed is None:
            self.changed = []
        if self.staged is None:
            self.staged = []
        if self.untracked is None:
            self.untracked = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "changed": self.changed,
            "staged": self.staged,
            "untracked": self.untracked,
            "has_changes": self.has_changes,
        }


class GitOps:
    """Git 自动化操作（subprocess 调 git）。

    用法：
        ops = GitOps(repo_path="/workspace")
        status = ops.status()
        if status.has_changes:
            ops.add_all()
            ops.commit("feat: 新功能")
    """

    def __init__(self, repo_path: str = ".") -> None:
        self._repo = repo_path

    def _run(self, args: list[str], check: bool = True) -> tuple[int, str, str]:
        """执行 git 命令。

        Returns:
            (returncode, stdout, stderr)
        """
        cmd = ["git"] + args
        try:
            proc = subprocess.run(
                cmd,
                cwd=self._repo,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if check and proc.returncode != 0:
                logger.warning(
                    "git 命令失败: %s → %s", " ".join(cmd), proc.stderr.strip()
                )
            # 注意：只去尾随换行，不去首部空格（git status --porcelain 输出首字符可能是空格）
            return proc.returncode, proc.stdout.rstrip("\n"), proc.stderr.rstrip("\n")
        except subprocess.TimeoutExpired:
            logger.exception("git 命令超时: %s", " ".join(cmd))
            return -1, "", "timeout"
        except FileNotFoundError:
            logger.exception("git 未安装或不在 PATH")
            return -2, "", "git not found"

    def is_repo(self) -> bool:
        """是否是 git 仓库。"""
        rc, _, _ = self._run(["rev-parse", "--is-inside-work-tree"], check=False)
        return rc == 0

    def current_branch(self) -> str:
        """当前分支名。"""
        rc, out, _ = self._run(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if rc != 0:
            return ""
        return out

    def status(self) -> GitStatus:
        """获取状态快照。"""
        rc, out, _ = self._run(["status", "--porcelain"], check=False)
        if rc != 0:
            return GitStatus()

        changed: list[str] = []
        staged: list[str] = []
        untracked: list[str] = []

        for line in out.splitlines():
            if not line:
                continue
            index_status = line[0] if len(line) > 0 else " "
            work_status = line[1] if len(line) > 1 else " "
            file_path = line[3:] if len(line) > 3 else line.strip()

            if index_status == "?" and work_status == "?":
                untracked.append(file_path)
            elif index_status not in (" ", "?"):
                staged.append(file_path)
            if work_status not in (" ", "?"):
                changed.append(file_path)

        return GitStatus(
            branch=self.current_branch(),
            changed=changed,
            staged=staged,
            untracked=untracked,
            has_changes=bool(changed or staged or untracked),
        )

    def has_changes(self) -> bool:
        """是否有未提交改动。"""
        return self.status().has_changes

    def _is_forbidden(self, path: str) -> bool:
        """判断文件是否在安全黑名单中。"""
        lower = path.lower()
        return any(p in lower for p in _FORBIDDEN_PATTERNS)

    def add(self, paths: list[str]) -> tuple[bool, list[str]]:
        """暂存指定文件（过滤黑名单）。

        Returns:
            (是否成功, 实际暂存的文件列表)
        """
        safe_paths = [p for p in paths if not self._is_forbidden(p)]
        skipped = [p for p in paths if self._is_forbidden(p)]
        if skipped:
            logger.warning("跳过敏感文件（安全黑名单）: %s", skipped)

        if not safe_paths:
            return True, []

        # 额外检查：禁止路径遍历
        for p in safe_paths[:]:
            if ".." in p or p.startswith("/") or (len(p) > 2 and p[1] == ":"):
                logger.warning("跳过路径遍历文件: %s", p)
                safe_paths.remove(p)

        if not safe_paths:
            return True, []

        rc, _, err = self._run(["add"] + safe_paths, check=False)
        if rc != 0:
            logger.error("git add 失败: %s", err)
            return False, []
        return True, safe_paths

    def add_all(self) -> tuple[bool, list[str]]:
        """暂存所有改动（过滤黑名单）。

        Returns:
            (是否成功, 实际暂存的文件列表)
        """
        status = self.status()
        all_files = status.staged + status.changed + status.untracked
        # 去重
        all_files = list(dict.fromkeys(all_files))
        return self.add(all_files)

    def commit(self, message: str) -> tuple[bool, str]:
        """提交。

        Args:
            message: commit message（支持多行）。

        Returns:
            (是否成功, commit sha 或错误信息)
        """
        rc, out, err = self._run(
            ["commit", "-m", message],
            check=False,
        )
        if rc != 0:
            # 无改动提交不算失败
            combined = (out + " " + err).lower()
            if "nothing to commit" in combined or "no changes" in combined:
                return True, "nothing to commit"
            return False, err
        # 提取 commit sha
        sha = self._get_last_sha()
        return True, sha

    def _get_last_sha(self) -> str:
        """获取最新 commit sha。"""
        rc, out, _ = self._run(["rev-parse", "HEAD"], check=False)
        return out[:12] if rc == 0 else ""

    def branch(self, name: str) -> bool:
        """创建分支。"""
        rc, _, _ = self._run(["branch", name], check=False)
        return rc == 0

    def checkout(self, name: str) -> bool:
        """切换分支。"""
        rc, _, _ = self._run(["checkout", name], check=False)
        return rc == 0

    def push(self, remote: str = "origin", branch: str = "") -> tuple[bool, str]:
        """推送（不自动 push --force）。

        Returns:
            (是否成功, 消息)
        """
        branch = branch or self.current_branch()
        if not branch:
            return False, "no branch"
        rc, _out, err = self._run(["push", remote, branch], check=False)
        if rc != 0:
            return False, err
        return True, f"pushed {branch} to {remote}"

    def stash(self) -> bool:
        """暂存当前改动（git stash push）。"""
        rc, _, _ = self._run(
            ["stash", "push", "-m", "bluedeer-auto-stash"], check=False
        )
        return rc == 0

    def stash_pop(self) -> bool:
        """恢复最近一次暂存（git stash pop）。"""
        rc, _, _ = self._run(["stash", "pop"], check=False)
        return rc == 0

    def merge_with_conflict_check(self, branch: str) -> tuple[bool, str]:
        """模拟合并并检测冲突（使用 --no-commit 做 dry-run）。

        Args:
            branch: 要合并的分支名。

        Returns:
            (无冲突?, 详情消息)
        """
        rc, _out, err = self._run(
            ["merge", "--no-commit", "--no-ff", branch], check=False
        )
        # 无论结果都 abort，模拟结束
        self._run(["merge", "--abort"], check=False)
        if rc != 0:
            return False, err or "检测到合并冲突"
        return True, "合并无冲突"

    def commit_with_message(self, msg: str) -> tuple[bool, str]:
        """带 commit message 的快捷提交包装。"""
        return self.commit(msg)


# ============== GitHubClient ==============


class GitHubClient:
    """GitHub REST API 客户端（urllib + token 鉴权）。

    需环境变量 GITHUB_TOKEN。无 token 时所有调用返回模拟结果。
    """

    API_BASE = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        self._has_token = bool(self._token)

    @property
    def has_token(self) -> bool:
        return self._has_token

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """发起 API 请求。

        Returns:
            (status_code, response_json)
        """
        url = f"{self.API_BASE}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._has_token:
            headers["Authorization"] = f"Bearer {self._token}"

        data = None
        if body is not None:
            # 脱敏后发送
            safe_body = sanitize_log(body)
            data = json.dumps(safe_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8") or "{}")
            except json.JSONDecodeError:
                err_body = {"error": str(e)}
            return e.code, err_body
        except (urllib.error.URLError, OSError) as e:
            return 0, {"error": str(e)}

    def create_pr(
        self,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str = "",
    ) -> tuple[bool, dict[str, Any]]:
        """创建 Pull Request。

        Args:
            repo: "owner/repo" 格式。
            title: PR 标题。
            head: 源分支。
            base: 目标分支。
            body: PR 描述（会脱敏）。

        Returns:
            (是否成功, 响应体)
        """
        if not self._has_token:
            logger.info("无 GITHUB_TOKEN，返回模拟 PR 结果")
            return True, {
                "mock": True,
                "title": title,
                "head": head,
                "base": base,
                "url": f"(mock) https://github.com/{repo}/pull/1",
            }

        payload = {"title": title, "head": head, "base": base, "body": body}
        status, resp = self._request("POST", f"/repos/{repo}/pulls", payload)
        return status == 201, resp

    def list_prs(
        self,
        repo: str,
        state: str = "open",
    ) -> tuple[bool, list[dict[str, Any]]]:
        """列 PR。

        Returns:
            (是否成功, PR 列表)
        """
        if not self._has_token:
            return True, [{"mock": True, "title": "(mock PR)"}]

        status, resp = self._request("GET", f"/repos/{repo}/pulls?state={state}")
        if status == 200 and isinstance(resp, list):
            return True, resp
        return False, []
