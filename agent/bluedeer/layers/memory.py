"""第 3 层：记忆层。进程内 dict，读写短期记忆。"""

import logging

from bluedeer.memory import InMemoryMemory

log = logging.getLogger(__name__)


class MemoryLayer:
    name = "memory"

    def __init__(self, memory=None):
        self.memory = memory or InMemoryMemory()

    def process(self, ctx):
        history = self.memory.get_short("history", [])
        ctx.memories = list(history[-5:])

        history.append(ctx.cleaned_input)
        history = history[-20:]
        self.memory.set_short("history", history)
        log.info("[memory] history_size=%d", len(history))
