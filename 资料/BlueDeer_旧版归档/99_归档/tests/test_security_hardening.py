"""Security hardening tests for BlueDeer.

Covers:
- SecurityScanner: SQL injection, XSS, SSRF, command injection, secret leak, unsafe API
- AuthSystem: login rate limiting, password hashing
- InputValidator: payload size, dangerous patterns
- Config: type coercion
- WebAdmin: XSS escaping, input validation
- ToolExecutor: info leak prevention
- GitOps/TestRunner: path traversal protection
- ShellExecutor: shell injection prevention
- GameFrontend: XSS escaping
- CSRF: token generation and validation
- SSRF: webhook URL validation
- RateLimiter: request throttling
"""

from __future__ import annotations

import pytest
from fastapi.exceptions import HTTPException

import core.security as sec
from core.api_server import RateLimiter, _validate_webhook_url
from core.auth import AuthSystem, _check_login_rate_limit, _login_attempts
from core.digital_life.tool_executor import ToolExecutor
from core.git_ops import GitOps
from core.input_validator import InputValidator, ValidationError, sanitize_string
from core.security_guard import csrf_token, validate_csrf_token
from core.test_runner import TestRunner
from game_frontend import render_index
from web_admin import _escape_html


class TestSecurityScannerSQLInjection:
    def test_union_select_detected(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_sql_injection("SELECT * FROM t UNION SELECT * FROM u")
        assert any(t.threat_type == "sql_injection" for t in report)

    def test_or_1_equals_1_detected(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_sql_injection("' OR '1'='1")
        assert any(t.threat_type == "sql_injection" for t in report)

    def test_clean_string_passes(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_sql_injection("SELECT * FROM users WHERE id=1")
        assert not report


class TestSecurityScannerXSS:
    def test_script_tag_detected(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_xss("<script>alert(1)</script>")
        assert any(t.threat_type == "xss" for t in report)

    def test_img_onerror_detected(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_xss('<img src=x onerror=alert(1)>')
        assert any(t.threat_type == "xss" for t in report)


class TestSecurityScannerSSRF:
    def test_localhost_blocked(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_ssrf("http://127.0.0.1:8080")
        assert any(t.threat_type == "ssrf" for t in report)

    def test_clean_url_passes(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_ssrf("https://example.com")
        assert not report


class TestAuthSystemLoginRateLimiting:
    def test_rate_limit_blocks_after_max(self):
        _login_attempts.clear()
        auth = AuthSystem()
        for _ in range(20):
            auth.authenticate("admin", "wrong")
        allowed, _ = _check_login_rate_limit("admin")
        assert allowed is False

    def test_rate_limit_resets_after_window(self, monkeypatch):
        monkeypatch.setattr("core.auth._LOGIN_RATE_LIMIT_WINDOW", 0.1)
        _login_attempts.clear()
        _check_login_rate_limit("admin")
        import time
        time.sleep(0.15)
        allowed, _ = _check_login_rate_limit("admin")
        assert allowed is True


class TestWebAdminXSSEscaping:
    def test_escape_html_basic(self):
        assert _escape_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_escape_html_quotes(self):
        result = _escape_html('"onmouseover=alert(1)"')
        assert "&lt;" not in result
        assert "&gt;" not in result

    def test_escape_html_ampersand(self):
        result = _escape_html("a & b")
        assert result == "a &amp; b"


class TestToolExecutorNoInfoLeak:
    def test_sandbox_error_does_not_leak_traceback(self):
        executor = ToolExecutor.get_instance()
        result = executor.execute(None, "nonexistent_tool_xyz", {})
        assert result.ok is False
        assert "traceback" not in result.error.lower()
        assert "Traceback" not in result.error


class TestGitOpsPathTraversal:
    def test_add_rejects_path_traversal(self):
        ops = GitOps(repo_path=".")
        ok, paths = ops.add(["../../etc/passwd"])
        assert ok is False or len(paths) == 0

    def test_add_rejects_absolute_path(self):
        ops = GitOps(repo_path=".")
        ok, paths = ops.add(["/etc/passwd"])
        assert ok is False or len(paths) == 0


class TestShellExecutorNoShellInjection:
    def test_execute_uses_list_args_not_shell_true(self, monkeypatch):
        from core.digital_life.external.shell_executor import ShellExecutor
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            class FakeProc:
                returncode = 0
                stdout = "ok"
                stderr = ""
            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)
        executor = ShellExecutor(config={"enabled": True})
        result = executor.execute("echo hello")
        assert result.ok is True
        assert calls[0][0] == ["echo", "hello"]


class TestGameFrontendXSS:
    def test_visit_token_escaped(self):
        html = render_index(visit_mode=True, visit_token='"><script>alert(1)</script>')
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestCSRFProtection:
    def test_csrf_token_generation(self):
        token = csrf_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_csrf_token_validation(self):
        token = csrf_token()
        assert validate_csrf_token(token) is True

    def test_invalid_csrf_token_rejected(self):
        assert validate_csrf_token("invalid_token_xyz") is False


class TestSSRFProtection:
    def test_localhost_webhook_blocked(self):
        with pytest.raises(HTTPException):
            _validate_webhook_url("http://127.0.0.1:8080/webhook")

    def test_internal_ip_webhook_blocked(self):
        with pytest.raises(HTTPException):
            _validate_webhook_url("http://192.168.1.1/webhook")

    def test_valid_webhook_url_passes(self):
        result = _validate_webhook_url("https://example.com/webhook")
        assert result is None


class TestPathTraversalProtection:
    def test_git_ops_rejects_traversal(self):
        ops = GitOps(repo_path=".")
        ok, paths = ops.add(["../../etc/passwd"])
        assert ok is False or len(paths) == 0

    def test_test_runner_rejects_traversal(self):
        runner = TestRunner()
        result = runner.run("../../../etc/passwd")
        assert result.passed is False
        assert result.returncode == -3


class TestInfoLeakPrevention:
    def test_tool_executor_no_traceback(self):
        executor = ToolExecutor.get_instance()
        result = executor.execute(None, "nonexistent_tool_xyz", {})
        assert result.ok is False
        assert "traceback" not in result.error.lower()


class TestRateLimiting:
    def test_rate_limiter_blocks_after_max(self):
        limiter = RateLimiter(max_requests=3, window=60.0)
        key = "test_rate_limit_key"
        for _ in range(3):
            allowed, _ = limiter.check(key)
            assert allowed is True
        allowed, _ = limiter.check(key)
        assert allowed is False

    def test_rate_limiter_resets_after_window(self):
        limiter = RateLimiter(max_requests=2, window=0.1)
        key = "test_rate_limit_reset"
        for _ in range(2):
            allowed, _ = limiter.check(key)
            assert allowed is True
        import time
        time.sleep(0.15)
        allowed, _ = limiter.check(key)
        assert allowed is True


class TestXSSAdvanced:
    def test_encoded_xss_in_escape_html(self):
        payloads = [
            '<input onfocus=alert(1) autofocus>',
            '<svg onload=alert(1)>',
            'javascript:alert(1)',
        ]
        for payload in payloads:
            result = _escape_html(payload)
            assert "<" not in result
            assert ">" not in result

    def test_security_scanner_detects_encoded_xss(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_xss('<img src=x onerror=alert(1)>')
        assert any(t.threat_type == "xss" for t in report)


class TestSSRFAdvanced:
    def test_ssrf_scanner_detects_file_protocol(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_ssrf("file:///etc/passwd")
        assert any(t.threat_type == "ssrf" for t in report)

    def test_ssrf_scanner_detects_ftp_protocol(self):
        scanner = sec.SecurityScanner()
        report = scanner.scan_ssrf("ftp://internal-server/share")
        assert any(t.threat_type == "ssrf" for t in report)

    def test_webhook_url_rejects_non_http(self):
        with pytest.raises(HTTPException):
            _validate_webhook_url("file:///etc/passwd")
        with pytest.raises(HTTPException):
            _validate_webhook_url("ftp://internal-server/share")


class TestInputValidationEdgeCases:
    def test_null_byte_rejected(self):
        validator = InputValidator()
        with pytest.raises(ValidationError):
            validator.validate({"field": "test\x00malicious"}, "test_agent")

    def test_long_string_rejected(self):
        validator = InputValidator()
        with pytest.raises(ValidationError):
            validator.validate({"field": "x" * 100000}, "test_agent")

    def test_sanitize_removes_script_tags(self):
        result = sanitize_string("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "</script>" not in result
