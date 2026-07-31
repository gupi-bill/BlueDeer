"""BlueDeer 安全风控引擎：静态扫描 + 高危拦截 + 日志脱敏 + 月度报告 + 二次确认。

P5 核心：用纯标准库正则实现 SQL 注入/路径遍历/XSS/密钥泄露四类静态扫描，
所有工具调用前置 SecurityGuard 校验，审计日志经 sanitize_log 脱敏后落盘。

P5 扩容（A 级）：
- 漏洞规则：4 类 → 10+ 大类、30+ 条静态规则
- 安全流程：新增二次确认机制（need_confirm）+ 月度安全报告生成器
- 安全角色：由戒备猬拆分静态扫描 / 运行时审计 / 密钥管理 3 个子岗位（见 modules/hedgehog/agent.py）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tools.base_tool import ToolCategory

logger = logging.getLogger("bluedeer.security")


# ---- 风险等级 ----

class RiskLevel(Enum):
    """威胁风险等级。"""
    SAFE = "safe"        # 无威胁
    LOW = "low"          # 低危（提示）
    MEDIUM = "medium"    # 中危（警告）
    HIGH = "high"        # 高危（拦截）


# 威胁类型 → 风险等级
_THREAT_RISK: dict[str, RiskLevel] = {
    # 原 4 类
    "sql_injection": RiskLevel.HIGH,
    "path_traversal": RiskLevel.HIGH,
    "xss": RiskLevel.MEDIUM,
    "secret_leak": RiskLevel.HIGH,
    # P5 扩容 6 个新大类
    "hardcoded": RiskLevel.MEDIUM,             # 硬编码端口/IP/密码
    "unsafe_api": RiskLevel.HIGH,              # eval/shell/pickle/yaml/xml 等不安全 API
    "weak_crypto": RiskLevel.MEDIUM,           # 弱加密/弱随机/SSL 关闭
    "unauthorized_access": RiskLevel.HIGH,     # 越权文件读写
    "undisinfected_log": RiskLevel.MEDIUM,     # 日志未脱敏
    "insecure_config": RiskLevel.MEDIUM,       # debug/CORS/权限配置不安全
}


# ---- 静态扫描正则（纯标准库 re） ----

# SQL 注入：经典 payload 关键字组合
_SQL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:'|\")\s*(?:or|and)\s+(?:'1'='1|1=1|'a'='a)", re.IGNORECASE),
    re.compile(r"\bunion\s+select\b", re.IGNORECASE),
    re.compile(r";\s*(?:drop|delete|insert|update)\s+", re.IGNORECASE),
    re.compile(r"--\s*$", re.IGNORECASE),
    re.compile(r"\bexec(?:ute)?\s*\(", re.IGNORECASE),
    re.compile(r"\bxp_cmdshell\b", re.IGNORECASE),
]

# 路径遍历：../ 或 ..\\
_PATH_TRAVERSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e%2f", re.IGNORECASE),
    re.compile(r"%2e%2e/", re.IGNORECASE),
    re.compile(r"\.\.%2f", re.IGNORECASE),
]

# XSS：脚本注入
_XSS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"\bon\w+\s*=\s*['\"]?[^'\"]*['\"]?", re.IGNORECASE),
    re.compile(r"<\s*iframe\b", re.IGNORECASE),
    re.compile(r"<\s*img[^>]+onerror", re.IGNORECASE),
    re.compile(r"document\.cookie", re.IGNORECASE),
]

# 密钥泄露：API Key / password / token / AKSK
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"\b(?:api[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?", re.IGNORECASE)),
    ("password", re.compile(r"\b(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^\s'\"]{6,}['\"]?", re.IGNORECASE)),
    ("token", re.compile(r"\b(?:access[_-]?token|secret[_-]?token|auth[_-]?token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{16,}['\"]?", re.IGNORECASE)),
    ("aksk", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("sk", re.compile(r"\bsk[_-][A-Za-z0-9]{20,}\b", re.IGNORECASE)),
]


# ============== P5 扩容：6 个新规则大类（30+ 条静态规则） ==============

# 硬编码类：端口 / IP / 密码 / 数据库连接串
_HARDCODED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 硬编码端口（绑定端口：bind/port=80/8080 等，排除 0/1 等无意义值）
    ("port", re.compile(r"\b(?:port|PORT|bind|listen)\s*[=:]\s*(\d{2,5})\b")),
    # 硬编码 IP（IPv4，排除 0.0.0.0/127.0.0.1 localhost 之外的内网常见）
    ("ip", re.compile(r"\b(?:host|HOST|server|SERVER)\s*[=:]\s*['\"]?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})['\"]?")),
    # 硬编码密码（变量名 password/pwd 后接明文字符串）
    ("password", re.compile(r"\b(?:password|passwd|pwd)\s*=\s*['\"][^'\"]{4,}['\"]", re.IGNORECASE)),
    # 硬编码数据库连接串（mysql/postgresql 等含明文密码）
    ("db_conn", re.compile(r"(?:mysql|postgres|redis|mongodb)://\w+:[^@'\"]+@", re.IGNORECASE)),
]

# 不安全 API 用法：eval/exec/pickle/yaml.load/xml.etree/subprocess shell 等
_UNSAFE_API_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # eval() 调用
    ("eval", re.compile(r"\beval\s*\(")),
    # exec() 调用
    ("exec", re.compile(r"\bexec\s*\(")),
    # os.system 调用
    ("os_system", re.compile(r"\bos\.system\s*\(")),
    # subprocess shell=True
    ("subprocess_shell", re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True", re.IGNORECASE)),
    # pickle.load 反序列化
    ("pickle", re.compile(r"\bpickle\.loads?\s*\(")),
    # yaml.load 不带 SafeLoader
    ("yaml_unsafe", re.compile(r"\byaml\.load\s*\((?![^)]*Loader)", re.IGNORECASE)),
    # XML 实体解析（XXE）
    ("xml_entity", re.compile(r"XMLParser\(.*?resolve_entities\s*=\s*True", re.IGNORECASE)),
    # innerHTML 写入（前端 XSS）
    ("inner_html", re.compile(r"\.innerHTML\s*=", re.IGNORECASE)),
]

# 加密弱项：md5/sha1 用于密码 / random.random 用于安全场景 / SSL 验证关闭
_WEAK_CRYPTO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # md5 用于密码哈希
    ("md5", re.compile(r"\bhashlib\.md5\s*\(", re.IGNORECASE)),
    # sha1 用于密码哈希
    ("sha1", re.compile(r"\bhashlib\.sha1\s*\(", re.IGNORECASE)),
    # random 模块用于加密场景（明显错误的伪随机源）
    ("insecure_random", re.compile(r"\brandom\.(choice|randint|random)\s*\((?![^)]*game)", re.IGNORECASE)),
    # SSL verify=False 关闭证书校验
    ("ssl_verify_disabled", re.compile(r"verify\s*=\s*False", re.IGNORECASE)),
    # requests 不校验证书
    ("requests_no_verify", re.compile(r"requests\.\w+\([^)]*verify\s*=\s*False", re.IGNORECASE)),
]

# 越权文件读写：open /etc/passwd / 写系统目录 / chmod 777
_UNAUTHORIZED_ACCESS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 读系统敏感文件
    ("read_system", re.compile(r"open\s*\(\s*['\"](?:/etc/passwd|/etc/shadow|/root/|/proc/self/environ)", re.IGNORECASE)),
    # 写系统目录（/etc/ /usr/ /bin/）
    ("write_system", re.compile(r"open\s*\(\s*['\"](?:/etc/|/usr/|/bin/|/sbin/|/boot/)", re.IGNORECASE)),
    # chmod 777
    ("chmod_777", re.compile(r"chmod\s*\([^)]*0o?777", re.IGNORECASE)),
    # 跨用户目录访问 /home/other
    ("cross_user", re.compile(r"open\s*\(\s*['\"](?:/home/(?!root))", re.IGNORECASE)),
]

# 日志未脱敏：直接打印 password/token 字段
_UNDISINFECTED_LOG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # print 密码字段
    ("print_password", re.compile(r"print\s*\([^)]*(?:password|passwd|pwd)", re.IGNORECASE)),
    # logger 输出 token
    ("log_token", re.compile(r"logger\.\w+\s*\([^)]*(?:token|apikey|api_key)", re.IGNORECASE)),
    # 异常信息含密码
    ("exception_secret", re.compile(r"raise\s+\w*Error\s*\([^)]*(?:password|secret|token)", re.IGNORECASE)),
    # 直接打印 dict 含敏感 key
    ("print_dict_secret", re.compile(r"print\s*\([^)]*\b(?:self\.)?(?:config|env|params)\b[^)]*\)", re.IGNORECASE)),
]

# 配置不安全：debug=True / CORS 通配 / ALLOWED_HOSTS=* / SESSION_COOKIE_SECURE=False
_INSECURE_CONFIG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # debug=True 在生产暴露
    ("debug_mode", re.compile(r"DEBUG\s*=\s*True", re.IGNORECASE)),
    # CORS 允许 *
    ("cors_wildcard", re.compile(r"CORS_ORIGIN_ALLOW_ALL\s*=\s*True|Access-Control-Allow-Origin:\s*\*", re.IGNORECASE)),
    # ALLOWED_HOSTS = ['*']
    ("allowed_hosts_wildcard", re.compile(r"ALLOWED_HOSTS\s*=\s*\[?\s*['\"]\*['\"]", re.IGNORECASE)),
    # SESSION_COOKIE_SECURE = False
    ("cookie_insecure", re.compile(r"SESSION_COOKIE_SECURE\s*=\s*False|CSRF_COOKIE_SECURE\s*=\s*False", re.IGNORECASE)),
    # SECRET_KEY 硬编码（Django 风格）
    ("secret_key_hardcoded", re.compile(r"SECRET_KEY\s*=\s*['\"][^'\"]{16,}['\"]", re.IGNORECASE)),
]

# 需脱敏的字段名（关键词匹配）
_SENSITIVE_KEY_WORDS: tuple[str, ...] = (
    "password", "passwd", "pwd", "secret",
    "token", "apikey", "api_key",
    "aksk", "access_key", "secret_key",
    "private_key", "credential",
)


@dataclass
class Threat:
    """单个威胁记录。"""
    threat_type: str          # sql_injection / path_traversal / xss / secret_leak
    risk: RiskLevel
    matched: str              # 命中的字符串（密钥类已截断）
    location: str = ""        # 命中位置描述

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_type": self.threat_type,
            "risk": self.risk.value,
            "matched": self.matched,
            "location": self.location,
        }


@dataclass
class SecurityReport:
    """综合扫描报告。"""
    target: str = ""          # 被扫描对象描述
    threats: list[Threat] = field(default_factory=list)
    scanned_at: float = 0.0

    @property
    def risk_level(self) -> RiskLevel:
        """综合风险等级 = 最高威胁等级。"""
        if not self.threats:
            return RiskLevel.SAFE
        priority = {RiskLevel.SAFE: 0, RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
        return max(self.threats, key=lambda t: priority[t.risk]).risk

    @property
    def passed(self) -> bool:
        """是否通过（无 HIGH 级威胁）。"""
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


# ============== SecurityScanner：静态扫描器 ==============

class SecurityScanner:
    """静态安全扫描器：纯标准库正则实现。

    支持 10 类扫描（P5 扩容：原 4 类 + 新 6 类）：
    - SQL 注入 / 路径遍历 / XSS / 密钥泄露（原 4 类）
    - 硬编码 / 不安全 API / 加密弱项 / 越权访问 / 日志未脱敏 / 配置不安全（P5 扩容）
    """

    def scan_sql_injection(self, text: str) -> list[Threat]:
        """扫描 SQL 注入模式。"""
        threats: list[Threat] = []
        for pat in _SQL_INJECTION_PATTERNS:
            for m in pat.finditer(text):
                threats.append(Threat(
                    threat_type="sql_injection",
                    risk=_THREAT_RISK["sql_injection"],
                    matched=m.group()[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_path_traversal(self, path: str) -> list[Threat]:
        """扫描路径遍历（../ 模式）。"""
        threats: list[Threat] = []
        for pat in _PATH_TRAVERSAL_PATTERNS:
            for m in pat.finditer(path):
                threats.append(Threat(
                    threat_type="path_traversal",
                    risk=_THREAT_RISK["path_traversal"],
                    matched=m.group()[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_xss(self, text: str) -> list[Threat]:
        """扫描 XSS 脚本注入。"""
        threats: list[Threat] = []
        for pat in _XSS_PATTERNS:
            for m in pat.finditer(text):
                threats.append(Threat(
                    threat_type="xss",
                    risk=_THREAT_RISK["xss"],
                    matched=m.group()[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_secret_leak(self, text: str) -> list[Threat]:
        """扫描密钥/密码/token 泄露。

        匹配串截断后只保留前 8 位 + ***，避免审计日志反成泄露源。
        """
        threats: list[Threat] = []
        for kind, pat in _SECRET_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()
                masked = raw[:8] + "***" if len(raw) > 8 else raw[:4] + "***"
                threats.append(Threat(
                    threat_type=f"secret_leak:{kind}",
                    risk=_THREAT_RISK["secret_leak"],
                    matched=masked,
                    location=f"pos={m.start()}",
                ))
        return threats

    # ============== P5 扩容：6 个新扫描方法 ==============

    def scan_hardcoded(self, text: str) -> list[Threat]:
        """P5 扩容：扫描硬编码端口/IP/密码/数据库连接串。"""
        threats: list[Threat] = []
        for kind, pat in _HARDCODED_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()
                # 硬编码密码需脱敏
                if kind == "password":
                    raw = raw[:12] + "***"
                threats.append(Threat(
                    threat_type=f"hardcoded:{kind}",
                    risk=_THREAT_RISK["hardcoded"],
                    matched=raw[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_unsafe_api(self, text: str) -> list[Threat]:
        """P5 扩容：扫描不安全 API 用法（eval/exec/pickle/yaml/xml/subprocess shell）。"""
        threats: list[Threat] = []
        for kind, pat in _UNSAFE_API_PATTERNS:
            for m in pat.finditer(text):
                threats.append(Threat(
                    threat_type=f"unsafe_api:{kind}",
                    risk=_THREAT_RISK["unsafe_api"],
                    matched=m.group()[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_weak_crypto(self, text: str) -> list[Threat]:
        """P5 扩容：扫描加密弱项（md5/sha1/弱随机/SSL 关闭）。"""
        threats: list[Threat] = []
        for kind, pat in _WEAK_CRYPTO_PATTERNS:
            for m in pat.finditer(text):
                threats.append(Threat(
                    threat_type=f"weak_crypto:{kind}",
                    risk=_THREAT_RISK["weak_crypto"],
                    matched=m.group()[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_unauthorized_access(self, text: str) -> list[Threat]:
        """P5 扩容：扫描越权文件读写（open 系统目录/chmod 777）。"""
        threats: list[Threat] = []
        for kind, pat in _UNAUTHORIZED_ACCESS_PATTERNS:
            for m in pat.finditer(text):
                threats.append(Threat(
                    threat_type=f"unauthorized_access:{kind}",
                    risk=_THREAT_RISK["unauthorized_access"],
                    matched=m.group()[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_undisinfected_log(self, text: str) -> list[Threat]:
        """P5 扩容：扫描日志未脱敏（print password/logger token）。"""
        threats: list[Threat] = []
        for kind, pat in _UNDISINFECTED_LOG_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()
                # 含密码/Token 需截断
                raw = raw[:20] + "***" if len(raw) > 20 else raw
                threats.append(Threat(
                    threat_type=f"undisinfected_log:{kind}",
                    risk=_THREAT_RISK["undisinfected_log"],
                    matched=raw,
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_insecure_config(self, text: str) -> list[Threat]:
        """P5 扩容：扫描配置不安全（debug=True/CORS */SECRET_KEY 硬编码）。"""
        threats: list[Threat] = []
        for kind, pat in _INSECURE_CONFIG_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group()
                # SECRET_KEY 硬编码需脱敏
                if kind == "secret_key_hardcoded":
                    raw = raw[:20] + "***"
                threats.append(Threat(
                    threat_type=f"insecure_config:{kind}",
                    risk=_THREAT_RISK["insecure_config"],
                    matched=raw[:80],
                    location=f"pos={m.start()}",
                ))
        return threats

    def scan_all(self, text: str, target: str = "") -> SecurityReport:
        """综合扫描：依次跑 10 类扫描（P5 扩容）。

        Args:
            text: 待扫描文本（代码/参数/路径）。
            target: 扫描目标描述（用于报告）。

        Returns:
            SecurityReport 综合报告。
        """
        import time
        threats: list[Threat] = []
        threats.extend(self.scan_sql_injection(text))
        threats.extend(self.scan_path_traversal(text))
        threats.extend(self.scan_xss(text))
        threats.extend(self.scan_secret_leak(text))
        # P5 扩容 6 类
        threats.extend(self.scan_hardcoded(text))
        threats.extend(self.scan_unsafe_api(text))
        threats.extend(self.scan_weak_crypto(text))
        threats.extend(self.scan_unauthorized_access(text))
        threats.extend(self.scan_undisinfected_log(text))
        threats.extend(self.scan_insecure_config(text))
        return SecurityReport(
            target=target or text[:50],
            threats=threats,
            scanned_at=time.time(),
        )

    def list_scan_categories(self) -> list[str]:
        """P5 扩容：列出所有扫描大类（10 个）。"""
        return [
            "sql_injection", "path_traversal", "xss", "secret_leak",
            "hardcoded", "unsafe_api", "weak_crypto",
            "unauthorized_access", "undisinfected_log", "insecure_config",
        ]

    # ============== CSRF 保护 + 请求验证 ==============

import secrets as _secrets
import hmac as _hmac

_CSRF_SECRET: str | None = None

def _get_csrf_secret() -> str:
    global _CSRF_SECRET
    if _CSRF_SECRET is None:
        _CSRF_SECRET = _secrets.token_hex(32)
    return _CSRF_SECRET

def csrf_token() -> str:
    """生成 CSRF token（HMAC-SHA256 签名）。"""
    import time as _time
    secret = _get_csrf_secret()
    t = str(int(_time.time()))
    sig = _hmac.new(secret.encode(), t.encode(), "sha256").hexdigest()[:12]
    return f"{t}.{sig}"

def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    """校验 CSRF token 是否有效且未过期。"""
    try:
        t_part, sig_part = token.split(".", 1)
        secret = _get_csrf_secret()
        expected = _hmac.new(secret.encode(), t_part.encode(), "sha256").hexdigest()[:12]
        if not _hmac.compare_digest(sig_part, expected):
            return False
        ts = int(t_part)
        return (time.time() - ts) <= max_age
    except (ValueError, OSError):
        return False

def validate_request(headers: dict[str, str], body: str) -> tuple[bool, str]:
    """中间件级请求验证：检查 CSRF token 并扫描 body。

    Returns:
        (是否通过, 原因)
    """
    token = (headers.get("X-CSRF-Token") or headers.get("x-csrf-token") or "")
    if not token:
        # 安全方法放行
        method = (headers.get("X-HTTP-Method") or headers.get("x-http-method") or "GET").upper()
        if method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return True, "ok（安全方法免检）"
        return False, "缺少 X-CSRF-Token"

    if not validate_csrf_token(token):
        return False, "X-CSRF-Token 无效或已过期"

    scanner = SecurityScanner()
    report = scanner.scan_all(body, target="request_body")
    if not report.passed:
        threats = [t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH]
        if threats:
            return False, f"请求 body 发现高危威胁: {threats}"

    return True, "ok"

def rule_count(self) -> int:
        """P5 扩容：返回当前规则总数（用于校验 30+ 目标）。"""
        return (
            len(_SQL_INJECTION_PATTERNS)
            + len(_PATH_TRAVERSAL_PATTERNS)
            + len(_XSS_PATTERNS)
            + len(_SECRET_PATTERNS)
            + len(_HARDCODED_PATTERNS)
            + len(_UNSAFE_API_PATTERNS)
            + len(_WEAK_CRYPTO_PATTERNS)
            + len(_UNAUTHORIZED_ACCESS_PATTERNS)
            + len(_UNDISINFECTED_LOG_PATTERNS)
            + len(_INSECURE_CONFIG_PATTERNS)
        )


# ============== SecurityGuard：高危拦截器 ==============

class SecurityGuard:
    """高危操作拦截器。

    在 MCPClient / ToolRegistry 调用工具前进行前置校验：
    1. HAZARDOUS 类工具必须显式允许名单。
    2. 对参数做静态安全扫描，发现 HIGH 级威胁即拒绝。
    3. Agent 权限校验：agent_id 是否有权限调该工具。

    P5 扩容：高危操作二次人工确认机制
    - HIGH 级威胁默认拒绝；若该次操作已携带 confirm_token 且 token 有效，放行
    - confirm_token 由 issue_confirm_token 颁发，单次有效，使用后失效
    """

    def __init__(
        self,
        scanner: SecurityScanner | None = None,
        allowed_hazardous_tools: set[str] | None = None,
        agent_permissions: dict[str, set[str]] | None = None,
        require_confirm_for_high: bool = True,
    ) -> None:
        self._scanner = scanner or SecurityScanner()
        # 允许调用的高危工具白名单（默认空，强制显式放行）
        self._allowed_hazardous = allowed_hazardous_tools or set()
        # agent_id → 允许调用的工具名集合；None 表示全允许
        self._agent_permissions = agent_permissions or {}
        # P5 扩容：HIGH 级威胁是否要求二次确认（默认开启）
        self._require_confirm = require_confirm_for_high
        # P5 扩容：已颁发的 confirm_token 集合（单次有效，用后即焚）
        self._confirm_tokens: set[str] = set()

    def allow_hazardous(self, tool_name: str) -> None:
        """将工具加入高危白名单。"""
        self._allowed_hazardous.add(tool_name)

    @property
    def agent_permissions(self) -> dict[str, set[str]]:
        """P0 修复：暴露 agent_id → 工具名集合 的权限映射（只读视图）。"""
        return self._agent_permissions

    def grant(self, agent_id: str, tool_name: str) -> None:
        """授予 agent 调用某工具的权限。"""
        self._agent_permissions.setdefault(agent_id, set()).add(tool_name)

    # ============== P5 扩容：二次确认机制 ==============

    def issue_confirm_token(self, reason: str = "") -> str:
        """P5 扩容：颁发高危操作二次确认 token。

        Args:
            reason: 颁发原因（仅记录，不参与校验）。

        Returns:
            一次性 token 字符串。
        """
        import secrets
        token = secrets.token_hex(8)
        self._confirm_tokens.add(token)
        logger.info("颁发二次确认 token（reason=%s）", reason)
        return token

    def revoke_confirm_token(self, token: str) -> bool:
        """P5 扩容：撤销未使用的 confirm token。"""
        if token in self._confirm_tokens:
            self._confirm_tokens.discard(token)
            return True
        return False

    def has_pending_confirm_tokens(self) -> int:
        """P5 扩容：返回当前未使用的 confirm token 数量。"""
        return len(self._confirm_tokens)

    def check_permission(self, agent_id: str, tool_name: str) -> tuple[bool, str]:
        """校验 agent 是否有权限调工具。

        语义：白名单模式
        - 整个权限表为空（未配置任何 agent）→ 默认放行（兼容 P1-P4 老链路）
        - 权限表非空但 agent 未配置 → 默认无权限
        - agent 已配置 → 校验工具是否在其权限集合内

        Returns:
            (是否允许, 原因)
        """
        # 整个权限表为空 → 放行（兼容 P1-P4）
        if not self._agent_permissions:
            return True, "ok"
        perms = self._agent_permissions.get(agent_id)
        if perms is None:
            # 权限表非空但 agent 未配置 → 拒绝
            return False, f"agent '{agent_id}' 未配置任何权限"
        if tool_name in perms:
            return True, "ok"
        return False, f"agent '{agent_id}' 无权调用工具 '{tool_name}'"

    def check_operation(
        self,
        tool_name: str,
        params: dict[str, Any],
        category: ToolCategory,
        confirm_token: str | None = None,
    ) -> tuple[bool, SecurityReport | None, str]:
        """前置校验单次工具调用。

        Args:
            tool_name: 工具名。
            params: 工具参数。
            category: 工具分级。
            confirm_token: P5 扩容。高危操作的二次确认 token；None 表示未确认。

        Returns:
            (是否放行, 扫描报告(可能为 None), 拒绝原因)

        P5 扩容语义：
        - 命中 HIGH 级威胁且 require_confirm_for_high=True 且未提供 token → 拒绝（need_confirm）
        - 命中 HIGH 级威胁且 token 有效 → 放行（token 用后即焚）
        - 命中 HIGH 级威胁且 token 无效 → 拒绝（invalid_token）
        """
        # HAZARDOUS 工具必须有白名单
        if category == ToolCategory.HAZARDOUS:
            if tool_name not in self._allowed_hazardous:
                return False, None, (
                    f"高危工具 '{tool_name}' 未在白名单，拒绝调用"
                )

        # 对所有参数值做静态扫描
        report: SecurityReport | None = None
        for k, v in params.items():
            if not isinstance(v, str):
                continue
            r = self._scanner.scan_all(v, target=f"param:{k}")
            if r.threats:
                if report is None:
                    report = r
                else:
                    report.threats.extend(r.threats)

        if report is not None and not report.passed:
            # P5 扩容：HIGH 级威胁二次确认分支
            if self._require_confirm:
                if confirm_token is None:
                    # 未提供 token：要求二次确认
                    return False, report, (
                        f"参数扫描发现 HIGH 级威胁，需二次确认: "
                        f"{[t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH]}"
                    )
                if confirm_token not in self._confirm_tokens:
                    # token 无效
                    return False, report, f"二次确认 token 无效: {confirm_token[:8]}***"
                # token 有效：用后即焚
                self._confirm_tokens.discard(confirm_token)
                logger.warning("HIGH 级威胁经二次确认放行: %s", tool_name)
                return True, report, "ok（经二次确认放行）"

            # 未开启二次确认：直接拒绝
            return False, report, (
                f"参数扫描发现 HIGH 级威胁: "
                f"{[t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH]}"
            )

        return True, report, "ok"


# ============== sanitize_log：日志脱敏 ==============

def sanitize_log(data: Any) -> Any:
    """递归脱敏日志数据。

    对 dict 中 key 名含敏感关键词的字段值替换为 '***'；
    对字符串中嵌入的密钥模式做截断脱敏。
    """
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            if _is_sensitive_key(str(k)):
                sanitized[k] = "***"
            else:
                sanitized[k] = sanitize_log(v)
        return sanitized
    if isinstance(data, list):
        return [sanitize_log(x) for x in data]
    if isinstance(data, str):
        return _sanitize_string(data)
    return data


def _is_sensitive_key(key: str) -> bool:
    """判断 key 名是否为敏感字段。"""
    lower = key.lower()
    return any(w in lower for w in _SENSITIVE_KEY_WORDS)


def _sanitize_string(text: str) -> str:
    """对字符串中嵌入的密钥模式做截断脱敏。"""
    for _, pat in _SECRET_PATTERNS:
        def _mask(m: re.Match[str]) -> str:
            raw = m.group()
            return raw[:8] + "***" if len(raw) > 8 else raw[:4] + "***"
        text = pat.sub(_mask, text)
    return text


# ============== P5 扩容：SecurityReportGenerator 月度安全报告 ==============

@dataclass
class SecurityAuditRecord:
    """P5 扩容：单次安全审计记录（用于月报聚合）。"""
    timestamp: float
    target: str
    risk_level: str           # safe/low/medium/high
    threat_count: int
    threat_types: list[str]   # ["sql_injection", "xss", ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "target": self.target,
            "risk_level": self.risk_level,
            "threat_count": self.threat_count,
            "threat_types": self.threat_types,
            "passed": self.passed,
        }


class SecurityReportGenerator:
    """P5 扩容：月度安全风险汇总报告生成器。

    职责：
    - 收集 SecurityReport / SecurityAuditRecord
    - 按威胁类型 / 风险等级 / 时间段聚合统计
    - 生成 Markdown 月度报告（含 TopN 高危目标、趋势、建议）
    """

    def __init__(self) -> None:
        self._records: list[SecurityAuditRecord] = []

    def add_report(self, report: SecurityReport) -> None:
        """从 SecurityReport 转换并追加记录。"""
        threat_types = []
        for t in report.threats:
            # threat_type 形如 "secret_leak:api_key"，取冒号前的大类
            base = t.threat_type.split(":")[0]
            if base not in threat_types:
                threat_types.append(base)
        self._records.append(SecurityAuditRecord(
            timestamp=report.scanned_at,
            target=report.target,
            risk_level=report.risk_level.value,
            threat_count=len(report.threats),
            threat_types=threat_types,
            passed=report.passed,
        ))

    def add_audit_record(self, record: SecurityAuditRecord) -> None:
        """直接追加审计记录。"""
        self._records.append(record)

    def clear(self) -> None:
        """清空记录。"""
        self._records.clear()

    @property
    def record_count(self) -> int:
        return len(self._records)

    def stats(self) -> dict[str, Any]:
        """聚合统计。"""
        if not self._records:
            return {
                "total": 0,
                "by_risk": {},
                "by_threat_type": {},
                "blocked_count": 0,
                "pass_rate": 0.0,
            }
        by_risk: dict[str, int] = {"safe": 0, "low": 0, "medium": 0, "high": 0}
        by_threat: dict[str, int] = {}
        blocked = 0
        passed = 0
        for r in self._records:
            by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1
            if not r.passed:
                blocked += 1
            else:
                passed += 1
            for t in r.threat_types:
                by_threat[t] = by_threat.get(t, 0) + 1
        return {
            "total": len(self._records),
            "by_risk": by_risk,
            "by_threat_type": by_threat,
            "blocked_count": blocked,
            "pass_rate": round(passed / len(self._records), 4),
        }

    def top_targets(self, n: int = 5) -> list[tuple[str, int]]:
        """TopN 高危目标（按 threat_count 降序）。"""
        sorted_recs = sorted(
            self._records,
            key=lambda r: r.threat_count,
            reverse=True,
        )
        return [(r.target, r.threat_count) for r in sorted_recs[:n]]

    def generate_markdown(self, period_label: str = "本月") -> str:
        """生成 Markdown 月度安全报告。

        Args:
            period_label: 报告周期标签（如 "2026-07"）。

        Returns:
            Markdown 字符串。
        """
        s = self.stats()
        lines: list[str] = [
            f"# 安全审计月度报告（{period_label}）",
            "",
            f"**审计次数**: {s['total']}",
            f"**拦截次数**: {s['blocked_count']}",
            f"**通过率**: {s['pass_rate'] * 100:.1f}%",
            "",
            "## 风险等级分布",
            "",
            "| 风险等级 | 次数 |",
            "|---|---|",
        ]
        for level in ("high", "medium", "low", "safe"):
            count = s["by_risk"].get(level, 0)
            lines.append(f"| {level} | {count} |")
        lines.append("")
        lines.append("## 威胁类型分布")
        lines.append("")
        lines.append("| 威胁类型 | 次数 |")
        lines.append("|---|---|")
        # 按次数降序
        sorted_threats = sorted(s["by_threat_type"].items(), key=lambda x: -x[1])
        for t, c in sorted_threats:
            lines.append(f"| {t} | {c} |")
        lines.append("")
        lines.append("## Top 5 高危目标")
        lines.append("")
        lines.append("| 目标 | 威胁数 |")
        lines.append("|---|---|")
        for target, count in self.top_targets(5):
            lines.append(f"| {target} | {count} |")
        lines.append("")
        lines.append("## 建议")
        lines.append("")
        if s["blocked_count"] > 0:
            lines.append(f"- 本期拦截 {s['blocked_count']} 次高危操作，建议复盘参数来源。")
        if s["by_threat_type"].get("sql_injection", 0) > 0:
            lines.append("- SQL 注入命中较多，建议推广参数化查询。")
        if s["by_threat_type"].get("secret_leak", 0) > 0:
            lines.append("- 密钥泄露命中较多，建议接入密钥管理服务。")
        if s["by_threat_type"].get("unsafe_api", 0) > 0:
            lines.append("- 不安全 API（eval/pickle 等）命中较多，建议代码评审强化禁用清单。")
        if not lines[-1].startswith("-"):
            lines.append("- 本期无高危命中，继续保持。")
        return "\n".join(lines) + "\n"
