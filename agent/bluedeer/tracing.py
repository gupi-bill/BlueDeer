"""运行追踪：每次 run 逐层落盘 JSON 快照，可回放、可排查。"""

import json
import time
import uuid
from pathlib import Path

from bluedeer.context import Context


class RunTrace:
    """一次 run 的追踪器：runs/<run_id>/ 下每层一个快照 + final.json。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.run_dir: Path | None = None
        self._order = 0

    def start(self) -> str:
        rid = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.run_dir = self.root / rid
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return rid

    def snapshot(self, layer_name: str, ctx: Context, elapsed_ms: int) -> None:
        if not self.run_dir:
            return
        data = {f: getattr(ctx, f) for f in Context.__dataclass_fields__}
        data["_layer"] = layer_name
        data["_elapsed_ms"] = elapsed_ms
        data["_ts"] = time.time()
        path = self.run_dir / f"{self._order:02d}_{layer_name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._order += 1

    def finish(self, ctx: Context) -> None:
        if not self.run_dir:
            return
        final = {
            "run_id": ctx.metadata.get("run_id"),
            "output": ctx.output,
            "blocked": ctx.blocked,
            "block_reason": ctx.block_reason,
            "layer_timings": ctx.metadata.get("layer_timings", {}),
            "finished_at": time.time(),
        }
        (self.run_dir / "final.json").write_text(
            json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
        )
