"""第 2 层：理解层。抽取实体（极简实现）。"""

import re


class UnderstandingLayer:
    name = "understanding"

    def process(self, ctx):
        text = ctx.cleaned_input
        ctx.entities = {
            "urls": re.findall(r"https?://\S+", text),
            "emails": re.findall(r"\S+@\S+\.\S+", text),
            "numbers": re.findall(r"\d+", text),
        }
