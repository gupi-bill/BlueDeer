"""BlueDeer 位图：稠密 + 稀疏 + 范围统计。

evolution（数据维度 - R187）：
- 用 list[bool] 占用每个元素 28 字节，1 百万位要 28MB
- 位图用每 8 位 1 字节存储，1 百万位仅 125KB
- 稠密模式：bytearray 顺序存储，set/get/count 都 O(1)
- 稀疏模式：dict 存非零位索引，大量 0 时省内存
- RLE 稀疏模式：游程编码压缩连续段
- 范围统计：count_range(start, end) 用 popcount 查表
- 典型用途：布隆过滤器底层、用户标签、签到打卡
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

# 8 位 popcount 查找表
_POPCOUNT8 = [(i).bit_count() for i in range(256)]


class Bitmap:
    """稠密位图。

    用法：
        bm = Bitmap(size=1000)
        bm.set(5, 1)
        assert bm.get(5) == 1
        assert bm.count() == 1
        bm.set_range(10, 20)
        assert bm.count_range(0, 100) == 11
        assert bm.find_first(1) == 5
    """

    def __init__(self, size: int = 0) -> None:
        if size < 0:
            raise ValueError("size 不能为负")
        self._size = size
        n_bytes = (size + 7) // 8
        self._data = bytearray(n_bytes)
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def _ensure_capacity(self, pos: int) -> None:
        if pos >= self._size:
            new_size = pos + 1
            new_n_bytes = (new_size + 7) // 8
            if new_n_bytes > len(self._data):
                self._data.extend(b"\x00" * (new_n_bytes - len(self._data)))
            self._size = new_size

    def set(self, pos: int, value: int = 1) -> None:
        if pos < 0:
            raise ValueError("pos 不能为负")
        with self._lock:
            self._ensure_capacity(pos)
            byte_idx = pos >> 3
            bit_idx = pos & 7
            if value:
                self._data[byte_idx] |= 1 << bit_idx
            else:
                self._data[byte_idx] &= ~(1 << bit_idx) & 0xFF

    def get(self, pos: int) -> int:
        if pos < 0 or pos >= self._size:
            return 0
        with self._lock:
            return (self._data[pos >> 3] >> (pos & 7)) & 1

    def batch_set(self, positions: list[int], value: int = 1) -> int:
        """批量设置位。返回实际设置数。"""
        if not positions:
            return 0
        with self._lock:
            count = 0
            for pos in positions:
                if pos < 0:
                    continue
                self._ensure_capacity(pos)
                byte_idx = pos >> 3
                bit_idx = pos & 7
                if value:
                    self._data[byte_idx] |= 1 << bit_idx
                else:
                    self._data[byte_idx] &= ~(1 << bit_idx) & 0xFF
                count += 1
            return count

    def batch_get(self, positions: list[int]) -> list[int]:
        """批量读取位。"""
        if not positions:
            return []
        with self._lock:
            return [
                (self._data[pos >> 3] >> (pos & 7)) & 1 if 0 <= pos < self._size else 0
                for pos in positions
            ]

    def set_range(self, start: int, end: int, value: int = 1) -> None:
        if start < 0:
            raise ValueError("start 不能为负")
        if end <= start:
            return
        with self._lock:
            self._ensure_capacity(end - 1)
            for pos in range(start, end):
                byte_idx = pos >> 3
                bit_idx = pos & 7
                if value:
                    self._data[byte_idx] |= 1 << bit_idx
                else:
                    self._data[byte_idx] &= ~(1 << bit_idx) & 0xFF

    def clear(self) -> None:
        with self._lock:
            for i in range(len(self._data)):
                self._data[i] = 0

    def count(self) -> int:
        with self._lock:
            return sum(_POPCOUNT8[b] for b in self._data)

    def count_range(self, start: int, end: int) -> int:
        start = max(start, 0)
        end = min(end, self._size)
        if end <= start:
            return 0
        with self._lock:
            n = 0
            while start < end and (start & 7) != 0:
                n += (self._data[start >> 3] >> (start & 7)) & 1
                start += 1
            while start + 8 <= end:
                n += _POPCOUNT8[self._data[start >> 3]]
                start += 8
            while start < end:
                n += (self._data[start >> 3] >> (start & 7)) & 1
                start += 1
            return n

    def find_first(self, value: int = 1) -> int:
        with self._lock:
            if value == 1:
                for byte_idx in range(len(self._data)):
                    b = self._data[byte_idx]
                    if b == 0:
                        continue
                    for bit_idx in range(8):
                        if b & (1 << bit_idx):
                            pos = (byte_idx << 3) + bit_idx
                            if pos < self._size:
                                return pos
                return -1
            else:
                for pos in range(self._size):
                    if not (self._data[pos >> 3] >> (pos & 7)) & 1:
                        return pos
                return -1

    def find_next(self, pos: int, value: int = 1) -> int:
        with self._lock:
            cur = pos
            while cur < self._size:
                bit = (self._data[cur >> 3] >> (cur & 7)) & 1
                if bit == value:
                    return cur
                cur += 1
            return -1

    def to_bytes(self) -> bytes:
        with self._lock:
            return bytes(self._data)

    @classmethod
    def from_bytes(cls, data: bytes, size: int | None = None) -> Bitmap:
        if size is None:
            size = len(data) * 8
        bm = cls(size)
        bm._data = bytearray(data)
        return bm

    def to_sparse(self) -> dict[int, int]:
        with self._lock:
            result = {}
            for byte_idx, b in enumerate(self._data):
                if b == 0:
                    continue
                for bit_idx in range(8):
                    if b & (1 << bit_idx):
                        pos = (byte_idx << 3) + bit_idx
                        if pos < self._size:
                            result[pos] = 1
            return result

    def density(self) -> float:
        if self._size == 0:
            return 0.0
        return self.count() / self._size

    def __iter__(self) -> Iterator[int]:
        with self._lock:
            for pos in range(self._size):
                yield (self._data[pos >> 3] >> (pos & 7)) & 1

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "byte_size": len(self._data),
                "ones": self.count(),
                "zeros": self._size - self.count(),
                "density": self.density(),
            }


class SparseBitmap:
    """稀疏位图：用 dict 存非零位索引。

    适用于位图极稀疏（密度 < 1%）的场景，节省内存。
    """

    def __init__(self) -> None:
        self._bits: dict[int, int] = {}
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def set(self, pos: int, value: int = 1) -> None:
        if pos < 0:
            raise ValueError("pos 不能为负")
        with self._lock:
            if pos >= self._size:
                self._size = pos + 1
            if value:
                self._bits[pos] = 1
            else:
                self._bits.pop(pos, None)

    def get(self, pos: int) -> int:
        with self._lock:
            return self._bits.get(pos, 0)

    def batch_set(self, positions: list[int], value: int = 1) -> int:
        if not positions:
            return 0
        with self._lock:
            count = 0
            for pos in positions:
                if pos < 0:
                    continue
                if pos >= self._size:
                    self._size = pos + 1
                if value:
                    self._bits[pos] = 1
                else:
                    self._bits.pop(pos, None)
                count += 1
            return count

    def batch_get(self, positions: list[int]) -> list[int]:
        if not positions:
            return []
        with self._lock:
            return [self._bits.get(pos, 0) for pos in positions]

    def set_range(self, start: int, end: int, value: int = 1) -> None:
        if start < 0:
            raise ValueError("start 不能为负")
        if end <= start:
            return
        with self._lock:
            self._size = max(self._size, end)
            for pos in range(start, end):
                if value:
                    self._bits[pos] = 1
                else:
                    self._bits.pop(pos, None)

    def clear(self) -> None:
        with self._lock:
            self._bits.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._bits)

    def count_range(self, start: int, end: int) -> int:
        with self._lock:
            return sum(1 for pos in self._bits if start <= pos < end)

    def find_first(self, value: int = 1) -> int:
        with self._lock:
            if value == 1:
                if not self._bits:
                    return -1
                return min(self._bits.keys())
            else:
                pos = 0
                sorted_set_bits = sorted(self._bits.keys())
                for b in sorted_set_bits:
                    if b > pos:
                        return pos
                    pos = b + 1
                return pos if pos < self._size else -1

    def find_next(self, pos: int, value: int = 1) -> int:
        with self._lock:
            if value == 1:
                for p in sorted(self._bits.keys()):
                    if p >= pos:
                        return p
                return -1
            else:
                cur = pos
                sorted_bits = sorted(self._bits.keys())
                for b in sorted_bits:
                    if b > cur:
                        return cur
                    cur = b + 1
                return cur if cur < self._size else -1

    def density(self) -> float:
        if self._size == 0:
            return 0.0
        return len(self._bits) / self._size

    def __iter__(self) -> Iterator[int]:
        with self._lock:
            return (self._bits.get(pos, 0) for pos in range(self._size))

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "ones": len(self._bits),
                "zeros": self._size - len(self._bits),
                "density": self.density(),
            }


class RLEBitmap:
    """游程编码稀疏位图。

    用 (start, length) 对表示连续 1 的段，密度极低时大幅压缩。
    """

    def __init__(self) -> None:
        self._runs: list[tuple[int, int]] = []
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def _is_set(self, pos: int) -> bool:
        for start, length in self._runs:
            if start <= pos < start + length:
                return True
        return False

    def set(self, pos: int, value: int = 1) -> None:
        if pos < 0:
            raise ValueError("pos 不能为负")
        with self._lock:
            if pos >= self._size:
                self._size = pos + 1
            if value:
                self._add_to_run(pos)
            else:
                self._remove_from_run(pos)

    def _add_to_run(self, pos: int) -> None:
        merged = False
        new_runs = []
        i = 0
        while i < len(self._runs):
            s, l = self._runs[i]
            if s + l < pos - 1:
                new_runs.append(self._runs[i])
                i += 1
            elif s > pos + 1:
                break
            else:
                start = min(s, pos)
                end = max(s + l, pos + 1)
                i += 1
                while i < len(self._runs):
                    ns, nl = self._runs[i]
                    if ns <= end + 1:
                        end = max(end, ns + nl)
                        i += 1
                    else:
                        break
                new_runs.append((start, end - start))
                merged = True
                break
        if not merged:
            new_runs.append((pos, 1))
        new_runs.extend(self._runs[i:])
        self._runs = new_runs

    def _remove_from_run(self, pos: int) -> None:
        new_runs = []
        for s, l in self._runs:
            if s + l <= pos or s > pos:
                new_runs.append((s, l))
            elif s < pos < s + l - 1:
                new_runs.append((s, pos - s))
                new_runs.append((pos + 1, s + l - pos - 1))
            elif s == pos:
                if l > 1:
                    new_runs.append((s + 1, l - 1))
            elif s + l - 1 == pos:
                new_runs.append((s, l - 1))
        self._runs = new_runs

    def get(self, pos: int) -> int:
        if pos < 0 or pos >= self._size:
            return 0
        with self._lock:
            return 1 if self._is_set(pos) else 0

    def batch_set(self, positions: list[int], value: int = 1) -> int:
        if not positions:
            return 0
        with self._lock:
            count = 0
            for pos in positions:
                if pos < 0:
                    continue
                if pos >= self._size:
                    self._size = pos + 1
                if value:
                    self._add_to_run(pos)
                else:
                    self._remove_from_run(pos)
                count += 1
            return count

    def batch_get(self, positions: list[int]) -> list[int]:
        if not positions:
            return []
        with self._lock:
            return [1 if self._is_set(pos) else 0 for pos in positions]

    def count(self) -> int:
        with self._lock:
            return sum(l for _, l in self._runs)

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()

    def density(self) -> float:
        if self._size == 0:
            return 0.0
        return self.count() / self._size

    def to_sparse(self) -> dict[int, int]:
        with self._lock:
            result = {}
            for s, l in self._runs:
                for p in range(s, s + l):
                    result[p] = 1
            return result

    def compressed_size(self) -> int:
        """RLE 压缩后的存储单元数。"""
        return len(self._runs)

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "ones": self.count(),
                "zeros": self._size - self.count(),
                "density": self.density(),
                "compressed_size": len(self._runs),
                "compression_ratio": (
                    f"{self._size / max(1, len(self._runs)):.1f}x"
                    if self._runs
                    else "N/A"
                ),
            }
