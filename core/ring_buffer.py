"""BlueDeer 环形缓冲区：固定容量 + SPSC 高性能 + 阻塞读。

evolution（数据维度 - R191）：
- list.append + pop(0) 头部出列是 O(n)
- deque 是 O(1)，但固定容量需要 maxlen，且不支持阻塞读
- 环形缓冲区用固定大小数组 + 头/尾指针，O(1) 入/出
- 单生产者单消费者（SPSC）场景下可无锁
- 多消费者场景加锁 + Condition，支持阻塞读
- 典型用途：日志缓冲、生产消费队列、流控
"""
from __future__ import annotations
import mmap
import threading
from typing import Any, Iterator, List


class RingBuffer:
    """固定容量环形缓冲区。

    用法：
        rb = RingBuffer(capacity=100)
        rb.put("msg")
        msg = rb.get()  # 阻塞读
        # 非阻塞
        msg = rb.get_nowait()
    """

    def __init__(self, capacity: int = 64) -> None:
        if capacity < 1:
            raise ValueError("capacity 必须 >= 1")
        self._capacity = capacity
        self._buffer: list[Any | None] = [None] * capacity
        self._head = 0
        self._tail = 0
        self._size = 0
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._closed = False
        self._total_put = 0
        self._total_get = 0
        self._total_dropped = 0

    def __len__(self) -> int:
        return self._size

    @property
    def capacity(self) -> int:
        return self._capacity

    def is_full(self) -> bool:
        with self._lock:
            return self._size >= self._capacity

    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> bool:
        with self._not_full:
            if self._closed:
                return False
            if self._size >= self._capacity:
                if not block:
                    self._total_dropped += 1
                    return False
                if not self._wait_not_full(timeout):
                    return False
                if self._closed:
                    return False
            self._buffer[self._tail] = item
            self._tail = (self._tail + 1) % self._capacity
            self._size += 1
            self._total_put += 1
            self._not_empty.notify()
            return True

    def put_nowait(self, item: Any) -> bool:
        return self.put(item, block=False)

    def put_overwrite(self, item: Any) -> bool:
        with self._lock:
            if self._closed:
                return False
            if self._size >= self._capacity:
                self._buffer[self._tail] = item
                self._tail = (self._tail + 1) % self._capacity
                self._head = (self._head + 1) % self._capacity
                self._total_dropped += 1
            else:
                self._buffer[self._tail] = item
                self._tail = (self._tail + 1) % self._capacity
                self._size += 1
            self._total_put += 1
            self._not_empty.notify()
            return True

    def write_batch(self, items: List[Any], block: bool = True, timeout: float | None = None) -> int:
        """批量写入。返回成功写入数。"""
        if not items:
            return 0
        with self._not_full:
            if self._closed:
                return 0
            written = 0
            for item in items:
                if self._size >= self._capacity:
                    if not block:
                        self._total_dropped += len(items) - written
                        break
                    if not self._wait_not_full(timeout):
                        self._total_dropped += len(items) - written
                        break
                    if self._closed:
                        break
                self._buffer[self._tail] = item
                self._tail = (self._tail + 1) % self._capacity
                self._size += 1
                self._total_put += 1
                written += 1
            if written > 0:
                self._not_empty.notify()
            return written

    def _wait_not_full(self, timeout: float | None) -> bool:
        if timeout is None:
            while self._size >= self._capacity and not self._closed:
                self._not_full.wait()
            return self._size < self._capacity
        end = None if timeout is None else __import__("time").time() + timeout
        while self._size >= self._capacity and not self._closed:
            if end is None:
                self._not_full.wait()
            else:
                rem = end - __import__("time").time()
                if rem <= 0:
                    return False
                self._not_full.wait(rem)
        return self._size < self._capacity

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        with self._not_empty:
            if self._size == 0:
                if not block:
                    return None
                if not self._wait_not_empty(timeout):
                    return None
            item = self._buffer[self._head]
            self._buffer[self._head] = None
            self._head = (self._head + 1) % self._capacity
            self._size -= 1
            self._total_get += 1
            self._not_full.notify()
            return item

    def get_nowait(self) -> Any:
        return self.get(block=False)

    def read_batch(self, count: int, block: bool = True, timeout: float | None = None) -> List[Any]:
        """批量读取最多 count 个元素。"""
        if count < 1:
            return []
        with self._not_empty:
            if self._size == 0:
                if not block:
                    return []
                if not self._wait_not_empty(timeout):
                    return []
            batch_size = min(count, self._size)
            result = []
            for _ in range(batch_size):
                item = self._buffer[self._head]
                self._buffer[self._head] = None
                self._head = (self._head + 1) % self._capacity
                self._size -= 1
                self._total_get += 1
                result.append(item)
            self._not_full.notify()
            return result

    def peek(self) -> Any:
        with self._lock:
            if self._size == 0:
                return None
            return self._buffer[self._head]

    def _wait_not_empty(self, timeout: float | None) -> bool:
        import time
        if timeout is None:
            while self._size == 0 and not self._closed:
                self._not_empty.wait()
            return self._size > 0
        end = time.time() + timeout
        while self._size == 0 and not self._closed:
            rem = end - time.time()
            if rem <= 0:
                return False
            self._not_empty.wait(rem)
        return self._size > 0

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._not_empty.notify_all()
            self._not_full.notify_all()

    def reopen(self) -> None:
        with self._lock:
            self._closed = False

    def clear(self) -> None:
        with self._lock:
            self._head = 0
            self._tail = 0
            self._size = 0
            for i in range(self._capacity):
                self._buffer[i] = None
            self._not_full.notify_all()

    def __iter__(self) -> Iterator[Any]:
        with self._lock:
            for i in range(self._size):
                idx = (self._head + i) % self._capacity
                yield self._buffer[idx]

    def to_list(self) -> list:
        return list(self)

    def mmap(self, path: str) -> None:
        """将缓冲区映射到内存映射文件。支持持久化。"""
        import os
        if self._size > 0:
            raise RuntimeError("mmap 只能用于空缓冲区")
        file_size = self._capacity * 8
        if os.path.exists(path):
            with open(path, "r+b") as f:
                m = mmap.mmap(f.fileno(), file_size)
                data = bytearray(m.read(file_size))
                m.close()
            self._buffer = list(data)
        else:
            with open(path, "wb") as f:
                f.write(b"\x00" * file_size)
            self._buffer = [None] * self._capacity
        self._mmap_path = path
        self._mmap_file_size = file_size

    def flush(self) -> None:
        """将当前缓冲区刷新到 mmap 文件（如果已映射）。"""
        if not hasattr(self, "_mmap_path") or not self._mmap_path:
            return
        import os
        if not os.path.exists(self._mmap_path):
            return
        with open(self._mmap_path, "r+b") as f:
            m = mmap.mmap(f.fileno(), self._mmap_file_size)
            for i in range(self._capacity):
                val = self._buffer[i]
                if val is not None and isinstance(val, int):
                    m[i] = val & 0xFF
            m.close()

    def status(self) -> dict:
        with self._lock:
            return {
                "capacity": self._capacity,
                "size": self._size,
                "is_full": self._size >= self._capacity,
                "is_empty": self._size == 0,
                "closed": self._closed,
                "total_put": self._total_put,
                "total_get": self._total_get,
                "total_dropped": self._total_dropped,
            }
