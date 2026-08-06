"""BlueDeer 安全静态扫描器：10 类规则，纯标准库 re 实现。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("bluedeer.security_scanner")


class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_THREAT_RISK: dict[str, RiskLevel] = {
    "sql_injection": RiskLevel.HIGH,
    "path_traversal": RiskLevel.HIGH,
    "xss": RiskLevel.MEDIUM,
    "secret_leak": RiskLevel.HIGH,
    "hardcoded": RiskLevel.MEDIUM,
    "unsafe_api": RiskLevel.HIGH,
    "weak_crypto": RiskLevel.MEDIUM,
    "unauthorized_access": RiskLevel.HIGH,
    "undisinfected_log": RiskLevel.MEDIUM,
    "insecure_config": RiskLevel.MEDIUM,
}

_SQL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:'|\")\s*(?:or|and)\s+(?:'1'='1|1=1|'a'='a)", re.IGNORECASE),
    re.compile(r"\bunion\s+select\b", re.IGNORECASE),
    re.compile(r";\s*(?:drop|delete|insert|update)\s+", re.IGNORECASE),
    re.compile(r"--\s*$", re.IGNORECASE),
    re.compile(r"\bxp_cmdshell\b", re.IGNORECASE),
]

_PATH_TRAVERSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e%2f", re.IGNORECASE),
    re.compile(r"%2e%2e/", re.IGNORECASE),
    re.compile(r"\.\.%2f", re.IGNORECASE),
]

_XSS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(
        r"\bon(?:click|error|load|mouseover|submit|change|input)\s*=", re.IGNORECASE
    ),
    re.compile(r"<\s*iframe\b", re.IGNORECASE),
    re.compile(r"<\s*img[^>]+onerror", re.IGNORECASE),
    re.compile(r"document\.cookie", re.IGNORECASE),
]

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "api_key",
        re.compile(
            r"\b(?:api[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?", re.IGNORECASE
        ),
    ),
    (
        "password",
        re.compile(
            r"\b(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^\s'\"]{6,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    (
        "token",
        re.compile(
            r"\b(?:access[_-]?token|secret[_-]?token|auth[_-]?token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{16,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    ("aksk", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("sk", re.compile(r"\bsk[_-][A-Za-z0-9]{20,}\b", re.IGNORECASE)),
]

_HARDCODED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("port", re.compile(r"\b(?:port|PORT|bind|listen)\s*[=:]\s*(\d{2,5})\b")),
    (
        "ip",
        re.compile(
            r"\b(?:host|HOST|server|SERVER)\s*[=:]\s*['\"]?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})['\"]?"
        ),
    ),
    (
        "password",
        re.compile(
            r"\b(?:password|passwd|pwd)\s*=\s*['\"][^'\"]{4,}['\"]", re.IGNORECASE
        ),
    ),
    (
        "db_conn",
        re.compile(r"(?:mysql|postgres|redis|mongodb)://\w+:[^@'\"]+@", re.IGNORECASE),
    ),
]

_UNSAFE_API_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("eval", re.compile(r"\beval\s*\(")),
    ("exec", re.compile(r"\bexec\s*\(")),
    ("os_system", re.compile(r"\bos\.system\s*\(")),
    (
        "subprocess_shell",
        re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True", re.IGNORECASE),
    ),
    ("pickle", re.compile(r"\bpickle\.loads?\s*\(")),
    ("yaml_unsafe", re.compile(r"\byaml\.load\s*\((?![^)]*Loader)", re.IGNORECASE)),
    (
        "xml_entity",
        re.compile(r"XMLParser\(.*?resolve_entities\s*=\s*True", re.IGNORECASE),
    ),
    ("inner_html", re.compile(r"\.innerHTML\s*=", re.IGNORECASE)),
]

_WEAK_CRYPTO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sha1", re.compile(r"\bhashlib\.sha1\s*\(", re.IGNORECASE)),
    ("ssl_verify_disabled", re.compile(r"verify\s*=\s*False", re.IGNORECASE)),
    (
        "requests_no_verify",
        re.compile(r"requests\.\w+\([^)]*verify\s*=\s*False", re.IGNORECASE),
    ),
]

_UNAUTHORIZED_ACCESS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "read_system",
        re.compile(
            r"open\s*\(\s*['\"](?:/etc/passwd|/etc/shadow|/root/|/proc/self/environ)",
            re.IGNORECASE,
        ),
    ),
    (
        "write_system",
        re.compile(
            r"open\s*\(\s*['\"](?:/etc/|/usr/|/bin/|/sbin/|/boot/)", re.IGNORECASE
        ),
    ),
    ("chmod_777", re.compile(r"chmod\s*\([^)]*0o?777", re.IGNORECASE)),
    ("cross_user", re.compile(r"open\s*\(\s*['\"](?:/home/(?!root))", re.IGNORECASE)),
]

_UNDISINFECTED_LOG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "print_password",
        re.compile(r"print\s*\([^)]*(?:password|passwd|pwd)", re.IGNORECASE),
    ),
    (
        "log_token",
        re.compile(r"logger\.\w+\s*\([^)]*(?:token|apikey|api_key)", re.IGNORECASE),
    ),
    (
        "exception_secret",
        re.compile(
            r"raise\s+\w*Error\s*\([^)]*(?:password|secret|token)", re.IGNORECASE
        ),
    ),
    (
        "print_dict_secret",
        re.compile(
            r"print\s*\([^)]*\b(?:self\.)?(?:config|env|params)\b[^)]*\)", re.IGNORECASE
        ),
    ),
]

_INSECURE_CONFIG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("debug_mode", re.compile(r"DEBUG\s*=\s*True", re.IGNORECASE)),
    (
        "cors_wildcard",
        re.compile(
            r"CORS_ORIGIN_ALLOW_ALL\s*=\s*True|Access-Control-Allow-Origin:\s*\*",
            re.IGNORECASE,
        ),
    ),
    (
        "allowed_hosts_wildcard",
        re.compile(r"ALLOWED_HOSTS\s*=\s*\[?\s*['\"]\*['\"]", re.IGNORECASE),
    ),
    (
        "cookie_insecure",
        re.compile(
            r"SESSION_COOKIE_SECURE\s*=\s*False|CSRF_COOKIE_SECURE\s*=\s*False",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_key_hardcoded",
        re.compile(r"SECRET_KEY\s*=\s*['\"][^'\"]{16,}['\"]", re.IGNORECASE),
    ),
]

_SENSITIVE_KEY_WORDS: tuple[str, ...] = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "aksk",
    "access_key",
    "secret_key",
    "private_key",
    "credential",
)


@dataclass
class Threat:
    threat_type: str
    risk: RiskLevel
    matched: str
    location: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_type": self.threat_type,
            "risk": self.risk.value,
            "matched": self.matched,
            "location": self.location,
        }


@dataclass
class SecurityReport:
    target: str = ""
    threats: list[Threat] = field(default_factory=list)
    scanned_at: float = 0.0

    @property
    def risk_level(self) -> RiskLevel:
        if not self.threats:
            return RiskLevel.SAFE
        priority = {
            RiskLevel.SAFE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }
        return max(self.threats, key=lambda t: priority[t.risk]).risk

    @property
    def passed(self) -> bool:
        return all(t.risk != RiskLevel.HIGH for t in self.threats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "risk_level": self.risk_level.value,
            "passed": self.passed,
            "threat_count": len(self.threats),
            "threats": [t.to_dict() for t in self.threats],
            "scanned_at": self.scanned_at,
        }


class SecurityScanner:
    def scan_sql_injection(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for pat in _SQL_INJECTION_PATTERNS:
            for m in pat.finditer(text):
                threats.append(
                    Threat(
                        "sql_injection",
                        _THREAT_RISK["sql_injection"],
                        m.group()[:80],
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_path_traversal(self, path: str) -> list[Threat]:
        threats: list[Threat] = []
        for pat in _PATH_TRAVERSAL_PATTERNS:
            for m in pat.finditer(path):
                threats.append(
                    Threat(
                        "path_traversal",
                        _THREAT_RISK["path_traversal"],
                        m.group()[:80],
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_xss(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for pat in _XSS_PATTERNS:
            for m in pat.finditer(text):
                threats.append(
                    Threat(
                        "xss", _THREAT_RISK["xss"], m.group()[:80], f"pos={m.start()}"
                    )
                )
        return threats

    def scan_secret_leak(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _SECRET_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()
                masked = raw[:8] + "***" if len(raw) > 8 else raw[:4] + "***"
                threats.append(
                    Threat(
                        f"secret_leak:{kind}",
                        _THREAT_RISK["secret_leak"],
                        masked,
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_hardcoded(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _HARDCODED_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()
                if kind == "password":
                    raw = raw[:12] + "***"
                threats.append(
                    Threat(
                        f"hardcoded:{kind}",
                        _THREAT_RISK["hardcoded"],
                        raw[:80],
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_unsafe_api(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _UNSAFE_API_PATTERNS:
            for m in pat.finditer(text):
                threats.append(
                    Threat(
                        f"unsafe_api:{kind}",
                        _THREAT_RISK["unsafe_api"],
                        m.group()[:80],
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_weak_crypto(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _WEAK_CRYPTO_PATTERNS:
            for m in pat.finditer(text):
                threats.append(
                    Threat(
                        f"weak_crypto:{kind}",
                        _THREAT_RISK["weak_crypto"],
                        m.group()[:80],
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_unauthorized_access(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _UNAUTHORIZED_ACCESS_PATTERNS:
            for m in pat.finditer(text):
                threats.append(
                    Threat(
                        f"unauthorized_access:{kind}",
                        _THREAT_RISK["unauthorized_access"],
                        m.group()[:80],
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_undisinfected_log(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _UNDISINFECTED_LOG_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()[:20] + "***" if len(m.group()) > 20 else m.group()
                threats.append(
                    Threat(
                        f"undisinfected_log:{kind}",
                        _THREAT_RISK["undisinfected_log"],
                        raw,
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_insecure_config(self, text: str) -> list[Threat]:
        threats: list[Threat] = []
        for kind, pat in _INSECURE_CONFIG_PATTERNS:
            for m in pat.finditer(text):
                raw = (
                    m.group()[:20] + "***"
                    if kind == "secret_key_hardcoded"
                    else m.group()[:80]
                )
                threats.append(
                    Threat(
                        f"insecure_config:{kind}",
                        _THREAT_RISK["insecure_config"],
                        raw,
                        f"pos={m.start()}",
                    )
                )
        return threats

    def scan_all(self, text: str, target: str = "") -> SecurityReport:
        import time

        threats: list[Threat] = []
        threats.extend(self.scan_sql_injection(text))
        threats.extend(self.scan_path_traversal(text))
        threats.extend(self.scan_xss(text))
        threats.extend(self.scan_secret_leak(text))
        threats.extend(self.scan_hardcoded(text))
        threats.extend(self.scan_unsafe_api(text))
        threats.extend(self.scan_weak_crypto(text))
        threats.extend(self.scan_unauthorized_access(text))
        threats.extend(self.scan_undisinfected_log(text))
        threats.extend(self.scan_insecure_config(text))
        return SecurityReport(
            target=target or text[:50], threats=threats, scanned_at=time.time()
        )

    def list_scan_categories(self) -> list[str]:
        return [
            "sql_injection",
            "path_traversal",
            "xss",
            "secret_leak",
            "hardcoded",
            "unsafe_api",
            "weak_crypto",
            "unauthorized_access",
            "undisinfected_log",
            "insecure_config",
        ]
