"""BlueDeer 员工游戏化档案。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.reward.progression import compute_level, get_level_perks


@dataclass(slots=True)
class AgentProfile:
    """员工游戏化档案。"""

    agent_id: str
    coins: int = 0
    exp: int = 0
    favor: int = 500
    total_tasks: int = 0
    success_count: int = 0
    failed_count: int = 0
    streak: int = 0  # 连续成功次数
    consecutive_fails: int = 0  # 连续失败次数（用于递增惩罚）
    code_lines: int = 0  # 累计生成代码行数
    dream_memories: int = 0  # 梦境固化记忆数
    dream_quality_high: int = 0  # 高质量梦境记忆数
    scan_count: int = 0  # 安全扫描次数
    block_count: int = 0  # 高危拦截次数
    token_saved: int = 0  # 累计节省 Token
    lowcost_ratio: float = 0.0  # 低成本模型调用占比（0-100）
    achievements: list[str] = field(default_factory=list)
    # P4 扩容：岗位行为计数（用于差异化奖励）
    code_fix_count: int = 0  # 代码修复次数
    commit_count: int = 0  # 规范提交次数
    test_pass_count: int = 0  # 测试通过次数
    token_overspend_penalty: int = 0  # 累计超额扣减金币

    @property
    def level(self) -> int:
        """等级（指数曲线）。"""
        return compute_level(self.exp)

    @property
    def perks(self) -> list[str]:
        """已解锁特权。"""
        return get_level_perks(self.level)

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        d = asdict(self)
        d["level"] = self.level
        d["perks"] = self.perks
        return d

    def to_stats(self) -> dict[str, Any]:
        """生成成就检查用的 stats 字典。"""
        return {
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "streak": self.streak,
            "consecutive_fails": self.consecutive_fails,
            "coins": self.coins,
            "exp": self.exp,
            "level": self.level,
            "favor": self.favor,
            "code_lines": self.code_lines,
            "dream_memories": self.dream_memories,
            "dream_quality_high": self.dream_quality_high,
            "scan_count": self.scan_count,
            "block_count": self.block_count,
            "token_saved": self.token_saved,
            "lowcost_ratio": self.lowcost_ratio,
            # P4 扩容字段
            "code_fix_count": self.code_fix_count,
            "commit_count": self.commit_count,
            "test_pass_count": self.test_pass_count,
        }
