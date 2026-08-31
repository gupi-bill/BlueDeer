"""BlueDeer 向量库 JSON 持久化。

P0 修复：
- save_to_disk / load_from_disk 支持可选 encrypt_key（XOR 加密，纯标准库）
- 新增 snapshot(path) / restore(path) 全量快照
"""

from __future__ import annotations

import json
import os
import time

from vector_db.vector_store import VectorStore


def _xor_bytes(data: bytes, key: str) -> bytes:
    """XOR 加解密（对称，纯标准库实现）。

    key 循环使用；空 key 返回原数据（兼容明文）。
    """
    if not key:
        return data
    kb = key.encode("utf-8")
    klen = len(kb)
    return bytes(b ^ kb[i % klen] for i, b in enumerate(data))


def save_to_disk(store: VectorStore, path: str, encrypt_key: str | None = None) -> None:
    """将向量库序列化到文件。

    Args:
        store: 向量库实例。
        path: 文件路径（如 vector_db/data/global.json）。
        encrypt_key: 加密密钥；None 表示明文 JSON，非空则 XOR 加密后写入二进制。
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = store.to_dict()
    if encrypt_key:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        with open(path, "wb") as f:
            f.write(_xor_bytes(raw, encrypt_key))
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def load_from_disk(path: str, encrypt_key: str | None = None) -> VectorStore:
    """从文件反序列化向量库。

    Args:
        path: 文件路径。
        encrypt_key: 加密密钥；None 表示按明文 JSON 读取，非空则按 XOR 解密。

    Returns:
        VectorStore 实例。文件不存在时返回空库。
    """
    if not os.path.exists(path):
        return VectorStore()
    if encrypt_key:
        with open(path, "rb") as f:
            raw = _xor_bytes(f.read(), encrypt_key)
        data = json.loads(raw.decode("utf-8"))
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    return VectorStore.from_dict(data)


def snapshot(store: VectorStore, path: str) -> None:
    """P0 修复：全量快照，把当前内存库状态写入指定路径（明文 JSON）。

    用于备份/回滚场景。父目录不存在会自动创建。

    Args:
        store: 向量库实例。
        path: 快照文件路径。
    """
    save_to_disk(store, path, encrypt_key=None)


def restore(path: str) -> VectorStore:
    """P0 修复：从快照恢复向量库（明文 JSON）。

    Args:
        path: 快照文件路径。

    Returns:
        VectorStore 实例。文件不存在时返回空库。
    """
    return load_from_disk(path, encrypt_key=None)


def backup(store: VectorStore, path: str) -> str:
    """导出全部向量数据到备份文件。

    在文件名中嵌入时间戳以避免覆盖。返回实际写入路径。

    Args:
        store: 向量库实例。
        path: 目标目录或文件路径。

    Returns:
        实际备份文件路径。
    """
    if os.path.isdir(path) or path.endswith(os.sep):
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(path, f"vector_backup_{ts}.json")
    save_to_disk(store, path)
    return path


def compress(store: VectorStore, path: str) -> str:
    """压缩向量库到磁盘（gzip 格式）。返回压缩文件路径。"""
    import gzip

    data = store.to_dict()
    raw = json.dumps(data, ensure_ascii=False)
    cpath = path if path.endswith(".gz") else path + ".gz"
    with gzip.open(cpath, "wt", encoding="utf-8") as f:
        f.write(raw)
    return cpath
