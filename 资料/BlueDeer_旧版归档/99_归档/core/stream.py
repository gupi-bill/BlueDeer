"""BlueDeer Stream 消息流：消费者组 + ACK + pending。

evolution（数据维度 - R189）：
- 简单队列：push 一次 pop 一次，消息丢了就丢了
- Stream 是持久化的：消息永久保留（直到主动删），多消费者独立消费进度
- 消费者组（ConsumerGroup）：
  - 多 consumer 共享一个进度（last_delivered_id）
  - 每条消息被组内一个 consumer 消费，进 PEL 待 ack
  - ack 后从 PEL 移除；未 ack 可被 claim 转给其他 consumer
- 模仿 Redis Stream 的 ID 格式："{毫秒时间戳}-{序号}"
- 典型用途：事件日志、任务分发、可靠消费
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar

T = TypeVar("T")


def _parse_id(id_str: str) -> tuple[int, int]:
    """解析 "{ms}-{seq}" 格式。"""
    if id_str == "-":
        return (0, 0)
    if id_str == "+":
        return (2**63 - 1, 2**63 - 1)
    if "-" not in id_str:
        return (int(id_str), 0)
    ms_str, seq_str = id_str.split("-", 1)
    return (int(ms_str), int(seq_str))


def _id_str(ms: int, seq: int) -> str:
    return f"{ms}-{seq}"


class StreamBuffer:
    """带背压的有界缓冲区。
    当队列满时 put 阻塞直到有空间。
    """

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = capacity
        self._buf: deque = deque()
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)
        self._closed = False

    def put(self, item: Any) -> None:
        """阻塞式写入。"""
        with self._not_full:
            while len(self._buf) >= self._capacity and not self._closed:
                self._not_full.wait()
            if self._closed:
                raise RuntimeError("StreamBuffer 已关闭")
            self._buf.append(item)
            self._not_empty.notify()

    def get(self) -> Any:
        """阻塞式读取。"""
        with self._not_empty:
            while not self._buf and not self._closed:
                self._not_empty.wait()
            if not self._buf and self._closed:
                raise RuntimeError("StreamBuffer 已关闭")
            item = self._buf.popleft()
            self._not_full.notify()
            return item

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._not_full.notify_all()
            self._not_empty.notify_all()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buf)

    @property
    def closed(self) -> bool:
        return self._closed


def batch(iterable: Iterable[T], n: int) -> Iterator[list[T]]:
    """将可迭代对象分成大小为 n 的块。
    Args:
        iterable: 任意可迭代对象。
        n: 块大小。
    Yields:
        list[T]。
    """
    chunk: list[T] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == n:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def throttle(iterable: Iterable[T], rate: float) -> Iterator[T]:
    """限制迭代速率（items/sec）。
    Args:
        iterable: 输入可迭代对象。
        rate: 每秒最多产生的元素数。
    Yields:
        T。
    """
    interval = 1.0 / rate if rate > 0 else 0.0
    for item in iterable:
        yield item
        if interval > 0:
            time.sleep(interval)


class Stream:
    """消息流。

    用法：
        s = Stream()
        msg_id = s.add({"event": "click", "user": "alice"})
        for mid, fields in s.range():
            print(mid, fields)
    """

    def __init__(self) -> None:
        self._entries: list[tuple[str, dict]] = []
        self._last_id = "0-0"
        self._lock = threading.RLock()
        self._groups: dict[str, ConsumerGroup] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, fields: dict, id: str = "*") -> str:
        """添加消息。id="*" 自动生成；指定 id 必须大于 last_id。"""
        with self._lock:
            if id == "*":
                new_id = self._next_id()
            else:
                if _parse_id(id) <= _parse_id(self._last_id):
                    raise ValueError(f"id {id} 必须 > last_id {self._last_id}")
                new_id = id
            self._entries.append((new_id, dict(fields)))
            self._last_id = new_id
            return new_id

    def add_many(self, items: list[dict]) -> list[str]:
        """批量添加。"""
        ids = []
        with self._lock:
            for fields in items:
                new_id = self._next_id()
                self._entries.append((new_id, dict(fields)))
                self._last_id = new_id
                ids.append(new_id)
        return ids

    def _next_id(self) -> str:
        ms = int(time.time() * 1000)
        last_ms, last_seq = _parse_id(self._last_id)
        if ms <= last_ms:
            ms = last_ms
            seq = last_seq + 1
        else:
            seq = 0
        return _id_str(ms, seq)

    def range(
        self,
        start: str = "-",
        end: str = "+",
        count: int = -1,
    ) -> list[tuple[str, dict]]:
        """返回 [start, end] 范围内的消息。"""
        with self._lock:
            start_id = _parse_id(start)
            end_id = _parse_id(end)
            result = []
            for mid, fields in self._entries:
                mid_parsed = _parse_id(mid)
                if start_id <= mid_parsed <= end_id:
                    result.append((mid, dict(fields)))
                    if count > 0 and len(result) >= count:
                        break
            return result

    def revrange(
        self,
        start: str = "+",
        end: str = "-",
        count: int = -1,
    ) -> list[tuple[str, dict]]:
        """反向范围查询。"""
        with self._lock:
            start_id = _parse_id(start)
            end_id = _parse_id(end)
            result = []
            for mid, fields in reversed(self._entries):
                mid_parsed = _parse_id(mid)
                if end_id <= mid_parsed <= start_id:
                    result.append((mid, dict(fields)))
                    if count > 0 and len(result) >= count:
                        break
            return result

    def __iter__(self) -> Iterator[tuple[str, dict]]:
        with self._lock:
            return iter(list(self._entries))

    def first_id(self) -> str | None:
        with self._lock:
            return self._entries[0][0] if self._entries else None

    def last_id(self) -> str | None:
        with self._lock:
            return self._entries[-1][0] if self._entries else None

    def trim(self, maxlen: int) -> int:
        """保留最近 maxlen 条。返回删除数。"""
        with self._lock:
            if len(self._entries) <= maxlen:
                return 0
            n = len(self._entries) - maxlen
            self._entries = self._entries[n:]
            return n

    def create_group(self, name: str, start: str = "0-0") -> ConsumerGroup:
        """创建消费者组。"""
        with self._lock:
            if name in self._groups:
                raise ValueError(f"组 {name} 已存在")
            g = ConsumerGroup(self, name, start)
            self._groups[name] = g
            return g

    def get_group(self, name: str) -> ConsumerGroup | None:
        with self._lock:
            return self._groups.get(name)

    def delete_group(self, name: str) -> bool:
        with self._lock:
            if name in self._groups:
                del self._groups[name]
                return True
            return False

    def status(self) -> dict:
        with self._lock:
            return {
                "length": len(self._entries),
                "first_id": self.first_id(),
                "last_id": self.last_id(),
                "groups": list(self._groups.keys()),
            }


class ConsumerGroup:
    """消费者组。

    用法：
        s = Stream()
        g = s.create_group("workers")
        msgs = g.read("worker-1", count=10)
        # 处理后 ack
        g.ack("worker-1", *[mid for mid, _ in msgs])
    """

    def __init__(self, stream: Stream, name: str, start: str = "0-0") -> None:
        self._stream = stream
        self._name = name
        self._last_delivered = start
        # PEL: id -> (consumer, fields, delivered_time)
        self._pel: dict[str, tuple[str, dict, float]] = {}
        # 每个 consumer 的 pending id 队列
        self._consumer_pel: dict[str, deque] = defaultdict(deque)
        self._lock = threading.RLock()
        self._delivered_count = 0
        self._acked_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def stream(self) -> Stream:
        return self._stream

    def read(
        self,
        consumer: str,
        count: int = 10,
        block: float | None = None,
    ) -> list[tuple[str, dict]]:
        """从未消费位置读取 count 条消息。block=None 立即返回。"""
        with self._lock:
            result: list[tuple[str, dict]] = []
            deadline = None if block is None else time.time() + block
            while len(result) < count:
                # 从 stream 拉 _last_delivered 之后的 count 条
                start_id = self._last_delivered
                entries = self._stream.range(
                    start=start_id,
                    end="+",
                    count=count - len(result) + 1,
                )
                # 跳过 start_id 自己（如果已存在）
                entries = [
                    (mid, fields)
                    for mid, fields in entries
                    if _parse_id(mid) > _parse_id(start_id)
                ]
                if not entries:
                    if block is None:
                        break
                    if deadline is not None and time.time() >= deadline:
                        break
                    time.sleep(0.01)
                    continue
                for mid, fields in entries:
                    if len(result) >= count:
                        break
                    self._pel[mid] = (consumer, dict(fields), time.time())
                    self._consumer_pel[consumer].append(mid)
                    result.append((mid, dict(fields)))
                    self._last_delivered = mid
                    self._delivered_count += 1
                if block is None:
                    break
            return result

    def ack(self, consumer: str, *ids: str) -> int:
        """确认消息。返回成功 ack 数。"""
        n = 0
        with self._lock:
            for mid in ids:
                entry = self._pel.get(mid)
                if entry is None:
                    continue
                c, _, _ = entry
                if c != consumer:
                    continue
                del self._pel[mid]
                try:
                    self._consumer_pel[consumer].remove(mid)
                except ValueError:
                    pass
                n += 1
                self._acked_count += 1
            return n

    def pending(self, consumer: str | None = None) -> list[str]:
        """返回 pending 的消息 id 列表。"""
        with self._lock:
            if consumer is None:
                return list(self._pel.keys())
            return list(self._consumer_pel.get(consumer, []))

    def pending_details(self, consumer: str | None = None) -> list[dict]:
        """返回 pending 详情。"""
        with self._lock:
            result = []
            for mid, (c, fields, t) in self._pel.items():
                if consumer is not None and c != consumer:
                    continue
                result.append(
                    {
                        "id": mid,
                        "consumer": c,
                        "fields": fields,
                        "delivered_at": t,
                        "idle": time.time() - t,
                    }
                )
            return result

    def claim(self, consumer_to: str, *ids: str) -> int:
        """将消息转移给其他 consumer。"""
        n = 0
        with self._lock:
            for mid in ids:
                entry = self._pel.get(mid)
                if entry is None:
                    continue
                c_from, fields, _ = entry
                if c_from == consumer_to:
                    continue
                try:
                    self._consumer_pel[c_from].remove(mid)
                except ValueError:
                    pass
                self._pel[mid] = (consumer_to, fields, time.time())
                self._consumer_pel[consumer_to].append(mid)
                n += 1
            return n

    def xclaim(self, consumer_to: str, min_idle: float, count: int = 100) -> list[str]:
        """自动 claim 闲置超过 min_idle 的消息。"""
        with self._lock:
            now = time.time()
            to_claim = []
            for mid, (c, fields, t) in list(self._pel.items()):
                if now - t >= min_idle:
                    to_claim.append(mid)
                    if len(to_claim) >= count:
                        break
            self.claim(consumer_to, *to_claim)
            return to_claim

    def reset(self) -> None:
        """重置组：清空 PEL 和消费进度。"""
        with self._lock:
            self._pel.clear()
            self._consumer_pel.clear()
            self._last_delivered = "0-0"
            self._delivered_count = 0
            self._acked_count = 0

    def status(self) -> dict:
        with self._lock:
            return {
                "name": self._name,
                "last_delivered": self._last_delivered,
                "pel_size": len(self._pel),
                "consumers": {c: len(p) for c, p in self._consumer_pel.items()},
                "delivered": self._delivered_count,
                "acked": self._acked_count,
            }
