"""第 1 层：输入层。清洗、截断、意图初判。"""

import logging
import re

log = logging.getLogger(__name__)


class InputLayer:
    name = "input"

    def process(self, ctx):
        text = ctx.raw_input.strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) > 8000:
            text = text[:8000]
        ctx.cleaned_input = text

        if text.startswith(("/", "!")):
            ctx.intent = "command"
        elif "?" in text or text.endswith("？"):
            ctx.intent = "question"
        else:
            ctx.intent = "chat"

        log.info("[input] intent=%s len=%d", ctx.intent, len(text))
