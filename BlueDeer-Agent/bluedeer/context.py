"""上下文对象：在 13 层之间流转的数据载体。"""

from dataclasses import dataclass, field


@dataclass
class Context:
    raw_input: str
    cleaned_input: str = ""
    intent: str = ""
    entities: dict = field(default_factory=dict)
    memories: list = field(default_factory=list)
    reasoning: str = ""
    decision: str = ""
    plan: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    action_result: str = ""
    result_ok: bool = True
    output: str = ""
    blocked: bool = False
    block_reason: str = ""
    flags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
