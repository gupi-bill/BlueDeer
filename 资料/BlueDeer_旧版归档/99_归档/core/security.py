"""BlueDeer 安全风控引擎：静态扫描 + 高危拦截 + 日志脱敏 + 月度报告 + 二次确认。

P5 拆分（008-2）：
- security_scanner.py：纯扫描规则 + Threat / SecurityReport / SecurityScanner
- security_guard.py：SecurityGuard + sanitize_log + CSRF + validate_request
- security_report.py：SecurityReportBuilder + SecurityReportGenerator（月度报告）
- security.py：兼容壳，重导出旧符号，避免 236 个 import 断链。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("bluedeer.security")

# ---- 兼容重导出：RiskLevel / Threat / SecurityReport（本地完整实现，见下） ----

__all__ = [
    "RiskLevel",
    "SecurityAuditRecord",
    # security_guard 导出
    "SecurityGuard",
    "SecurityReport",
    "SecurityReportBuilder",
    "SecurityReportGenerator",
    "SecurityScanner",
    # security_report 导出
    "SecurityThresholds",
    "Threat",
    "csrf_token",
    "sanitize_log",
    "validate_csrf_token",
    "validate_request",
]

# ---- security_guard 导出 ----
from core.security_guard import (
    SecurityGuard,
    csrf_token,
    sanitize_log,
    validate_csrf_token,
    validate_request,
)

# ---- security_report 导出 ----
from core.security_report import (
    SecurityAuditRecord,
    SecurityReportBuilder,
    SecurityReportGenerator,
    SecurityThresholds,
)

# ---- security_scanner 导出（单一来源，避免双重枚举） ----
from core.security_scanner import RiskLevel, SecurityReport, SecurityScanner, Threat
