"""第一版记忆层：进程内 dict，不持久化。"""


class InMemoryMemory:
    def __init__(self):
        self._short = {}
        self._long = {}

    def set_short(self, key: str, value):
        self._short[key] = value

    def get_short(self, key: str, default=None):
        return self._short.get(key, default)

    def set_long(self, key: str, value):
        self._long[key] = value

    def get_long(self, key: str, default=None):
        return self._long.get(key, default)

    def all_short(self) -> dict:
        return dict(self._short)
