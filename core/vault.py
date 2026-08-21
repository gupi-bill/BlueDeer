"""企业级密钥集中管理 vault。

- 所有 API key / token / 密码统一存 data/vault.json（字段级加密）。
- 主密钥：环境变量 BLUEDEER_MASTER_KEY 优先，否则 data/.master_key（自动生成）。
- 提供 get / set / delete / mask / scan_plaintext_secrets。
- 使用 cryptography.Fernet（已依赖，离线可用），不可用时降级 base64 异或。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from typing import Any

logger = logging.getLogger("bluedeer.vault")

_VAULT_FILE = "data/vault.json"
_MASTER_KEY_FILE = "data/.master_key"
_ENV_KEY = "BLUEDEER_MASTER_KEY"

_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|api[_-]?secret|token|password|secret|私钥|密钥)\s*[=:]\s*[\"']?([A-Za-z0-9_\-]{8,})",
    re.IGNORECASE,
)


def _xor_encrypt(plain: str, key: bytes) -> str:
    data = plain.encode("utf-8")
    rep = (key * (len(data) // len(key) + 1))[: len(data)]
    return base64.urlsafe_b64encode(
        bytes(a ^ b for a, b in zip(data, rep))
    ).decode("ascii")


def _xor_decrypt(cipher: str, key: bytes) -> str:
    data = base64.urlsafe_b64decode(cipher.encode("ascii"))
    rep = (key * (len(data) // len(key) + 1))[: len(data)]
    return bytes(a ^ b for a, b in zip(data, rep)).decode("utf-8")


class Vault:
    def __init__(self, vault_file: str = _VAULT_FILE, master_key_file: str = _MASTER_KEY_FILE) -> None:
        self._vault_file = vault_file
        self._master_key_file = master_key_file
        self._lock = threading.RLock()
        self._data: dict[str, str] = {}
        self._fernet = None
        self._master_key = self._load_or_create_master_key()
        self._init_crypto()
        self._load()

    # ---- 主密钥 ----
    def _load_or_create_master_key(self) -> bytes:
        env_key = os.environ.get(_ENV_KEY, "").strip()
        if env_key:
            return self._derive_key(env_key)
        os.makedirs(os.path.dirname(self._master_key_file) or ".", exist_ok=True)
        if os.path.exists(self._master_key_file):
            with open(self._master_key_file, "rb") as f:
                raw = f.read().strip()
            if raw:
                return raw
        raw = base64.urlsafe_b64encode(os.urandom(32))
        with open(self._master_key_file, "wb") as f:
            f.write(raw)
        return raw

    @staticmethod
    def _derive_key(secret: str) -> bytes:
        import hashlib

        return base64.urlsafe_b64encode(
            hashlib.sha256(secret.encode("utf-8")).digest()
        )

    def _init_crypto(self) -> None:
        try:
            from cryptography.fernet import Fernet

            # 确保 32 字节 urlsafe base64 key
            key = self._master_key
            if len(base64.urlsafe_b64decode(key)) != 32:
                key = self._derive_key(key.decode("ascii", errors="ignore"))
            self._fernet = Fernet(key)
            logger.info("vault 使用 Fernet 加密")
        except Exception as e:
            self._fernet = None
            logger.warning("Fernet 不可用，vault 降级为 XOR 混淆: %s", e)

    # ---- 加解密 ----
    def _encrypt(self, plain: str) -> str:
        if self._fernet is not None:
            return self._fernet.encrypt(plain.encode("utf-8")).decode("ascii")
        return "xor:" + _xor_encrypt(plain, self._master_key)

    def _decrypt(self, cipher: str) -> str:
        try:
            if cipher.startswith("xor:"):
                return _xor_decrypt(cipher[4:], self._master_key)
            if self._fernet is not None:
                return self._fernet.decrypt(cipher.encode("ascii")).decode("utf-8")
        except Exception as e:
            logger.warning("vault 解密失败: %s", e)
        return ""

    # ---- 存储 ----
    def _load(self) -> None:
        if not os.path.exists(self._vault_file):
            self._data = {}
            return
        try:
            with open(self._vault_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._vault_file) or ".", exist_ok=True)
        with open(self._vault_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ---- 公共 API ----
    def get(self, name: str, default: str = "") -> str:
        with self._lock:
            cipher = self._data.get(name)
            if cipher is None:
                return default
            val = self._decrypt(cipher)
            return val if val else default

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self._data[name] = self._encrypt(value)
            self._save()

    def delete(self, name: str) -> bool:
        with self._lock:
            if name in self._data:
                del self._data[name]
                self._save()
                return True
            return False

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._data.keys())

    def mask(self, value: str) -> str:
        """脱敏：保留头尾少量字符，中间打码。"""
        if not value:
            return ""
        if len(value) <= 6:
            return "*" * len(value)
        return value[:3] + "***" + value[-3:]

    def mask_all(self) -> dict[str, str]:
        """返回所有 key 的脱敏值（用于日志/接口展示）。"""
        return {k: self.mask(self.get(k)) for k in self.keys()}

    @staticmethod
    def scan_plaintext_secrets(text: str) -> list[str]:
        """扫描文本中的明文密钥命中，返回 key 名列表。"""
        hits = []
        for m in _SECRET_KEY_RE.finditer(text):
            key_name = m.group(1)
            if key_name and len(key_name) >= 8:
                hits.append(key_name)
        return hits


def mask_secret(value: str) -> str:
    """便捷脱敏函数（config 输出/日志/API 返回用）。"""
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return value[:3] + "***" + value[-3:]


_vault_singleton: Vault | None = None
_vault_lock = threading.Lock()


def get_vault() -> Vault:
    global _vault_singleton
    with _vault_lock:
        if _vault_singleton is None:
            _vault_singleton = Vault()
        return _vault_singleton
