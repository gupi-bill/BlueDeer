"""灵音雀自动巡检播报器 + 历史持久化。

能力：
1. 定时全自动全局巡检（轻度 5min / 深度 30min）
2. 异常主动触发告警推送（轻/中/重三级）
3. 任务节点自动播报（启动/生成完成/测试通过/Git推送/重构落地/梦境固化）
4. 巡检历史持久化到 sparrow_logs/（联动 RAG 复盘）
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from modules.sparrow.status_center import StatusCenter, SystemSnapshot

logger = logging.getLogger("bluedeer.sparrow.announcer")


# ============== 告警等级 ==============


class AlertLevel(Enum):
    """告警三级。"""

    LIGHT = "light"  # 轻度：单员工少量报错、Token 小幅上涨
    MEDIUM = "medium"  # 中度：测试连续失败、梦境产出劣质
    HEAVY = "heavy"  # 重度：高危安全操作、流水线卡死、模型 API 中断


# ============== 播报模板 ==============

# 基础 6 套播报文案模板
_BROADCAST_TEMPLATES: dict[str, str] = {
    "task_start": "🚀 任务启动: {task_id} | 类型: {task_type} | 指派: {assignee}",
    "code_generated": "✍️ 代码生成完成: {task_id} | 模型: {model} | Token: {tokens}",
    "test_passed": "✅ 测试通过: {test_path} | 通过数: {passed_count}",
    "git_pushed": "📦 Git 推送成功: {branch} | 提交: {commit_hash}",
    "refactor_landed": "🔧 架构重构落地: {module} | 影响范围: {scope}",
    "dream_solidified": "💤 梦境固化完成: {dream_id} | 阶段: {stage}",
}

# 扩充 32 套分场景播报模板（代码/美术/安全/运维/梦境/成本 6 专项）
_BROADCAST_TEMPLATES_EXTENDED: dict[str, str] = {
    # 代码专项
    "code_review": "🔍 代码评审: {file} | 问题数: {issues}",
    "code_merge": "🔀 代码合并: {branch} → main",
    "code_rollback": "⏪ 代码回滚: {commit_hash} | 原因: {reason}",
    "code_lint": "🧹 Lint 检查: {file} | 警告: {warnings}",
    "code_coverage": "📊 覆盖率: {module} | {rate}%",
    "code_duplication": "🔁 重复代码: {file} | {rate}%",
    # 美术专项
    "art_asset_added": "🎨 素材新增: {asset} | 尺寸: {size}",
    "art_palette_updated": "🎨 调色板更新: {palette}",
    "art_animation_done": "🎨 动画完成: {sprite} | 帧数: {frames}",
    "art_spec_violation": "⚠️ 美术规范违反: {asset} | 问题: {issue}",
    "art_export": "🎨 素材导出: {count} 个",
    # 安全专项
    "security_scan_done": "🛡️ 安全扫描完成: 扫描 {count} 文件 | 拦截 {blocked}",
    "security_vulnerability": "🚨 漏洞发现: {type} | 文件: {file}",
    "security_blocked": "🚫 高危操作拦截: {tool} | 原因: {reason}",
    "security_confirmed": "🔐 二次确认通过: {tool}",
    "security_report": "📋 安全月报: 拦截 {blocked} | 通过率 {rate}%",
    # 运维专项
    "ops_deploy": "🚀 部署: {env} | 版本: {version}",
    "ops_restart": "🔄 服务重启: {service}",
    "ops_backup": "💾 备份完成: {target}",
    "ops_health_check": "❤️ 健康检查: {service} | 状态: {status}",
    "ops_resource_alert": "⚠️ 资源告警: {resource} | 占用: {rate}%",
    # 梦境专项
    "dream_start": "💤 梦境推演启动: {dream_id} | 岗位: {role}",
    "dream_stage": "💤 梦境阶段: {stage} | 进度: {progress}%",
    "dream_nightmare": "😱 噩梦告警: {dream_id} | 问题: {issue}",
    "dream_archive": "📚 梦境归档: {dream_id} | 价值: {value}",
    "dream_cross_role": "💤 跨岗位梦境: {roles} | 主题: {topic}",
    # 成本专项
    "cost_daily": "💰 日成本: {tokens} Token | {cost} 元",
    "cost_overrun": "⚠️ 成本超限: {module} | 超出: {percent}%",
    "cost_optimization": "💎 成本优化: {module} | 节省: {tokens} Token",
    "cost_model_switch": "🔄 模型切换: {from_model} → {to_model} | 原因: 节省成本",
    "cost_report": "📋 成本月报: 总消耗 {tokens} | 预算 {budget}",
    "cost_alert_threshold": "⚠️ 成本阈值告警: 已用 {percent}% 预算",
}


# ============== 巡检记录 ==============


@dataclass
class InspectionRecord:
    """单次巡检记录。"""

    timestamp: float
    kind: str  # light_brief / deep_report / alert / node_broadcast
    level: str = ""  # 告警等级（仅 alert 类型）
    content: str = ""  # 巡检内容/告警消息
    snapshot: dict[str, Any] = field(default_factory=dict)  # 伴随快照

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "level": self.level,
            "content": self.content,
            "snapshot": self.snapshot,
        }


# ============== 巡检播报器 ==============


class SparrowAnnouncer:
    """灵音雀自动巡检播报器。

    三大能力：
    1. 定时巡检：light（5min）/ deep（30min）
    2. 异常告警：检测到风险立刻触发，三级告警
    3. 节点播报：流水线关键节点自动播报

    持久化：所有记录写入 sparrow_logs/，联动 RAG 复盘历史故障。
    """

    # 巡检周期默认值
    LIGHT_INTERVAL = 300.0  # 5 分钟
    DEEP_INTERVAL = 1800.0  # 30 分钟

    def __init__(
        self,
        status_center: StatusCenter,
        broadcast_callback: Any | None = None,
        logs_dir: str = "sparrow_logs",
        rag_system: Any | None = None,
    ) -> None:
        self._status = status_center
        self._broadcast = broadcast_callback  # 通常传入 VoiceSparrowAgent.broadcast
        self._logs_dir = logs_dir
        self._rag = rag_system
        self._records: list[InspectionRecord] = []
        self._running = False
        self._light_task: asyncio.Task | None = None
        self._deep_task: asyncio.Task | None = None
        self._light_interval = self.LIGHT_INTERVAL
        self._deep_interval = self.DEEP_INTERVAL
        self._ensure_logs_dir()

    def _ensure_logs_dir(self) -> None:
        """确保日志目录存在。"""
        os.makedirs(self._logs_dir, exist_ok=True)

    # ============== 历史持久化 ==============

    @property
    def records(self) -> list[InspectionRecord]:
        return list(self._records)

    @property
    def record_count(self) -> int:
        return len(self._records)

    def _add_record(self, record: InspectionRecord) -> None:
        """追加记录并持久化。"""
        self._records.append(record)
        if len(self._records) > 1000:
            self._records = self._records[-1000:]
        self._persist_record(record)

    def _persist_record(self, record: InspectionRecord) -> None:
        """单条记录持久化到日志文件。"""
        date_str = time.strftime("%Y%m%d", time.localtime(record.timestamp))
        filename = f"{self._logs_dir}/sparrow_{date_str}.jsonl"
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("持久化巡检记录失败: %s", e)

    def query_history(
        self,
        kind: str | None = None,
        level: str | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 100,
    ) -> list[InspectionRecord]:
        """查询历史记录。

        Args:
            kind: 按类型过滤（light_brief/deep_report/alert/node_broadcast）。
            level: 按告警等级过滤。
            since: 起始时间戳。
            until: 截止时间戳。
            limit: 最多返回条数。
        """
        result = []
        for r in reversed(self._records):
            if kind and r.kind != kind:
                continue
            if level and r.level != level:
                continue
            if since and r.timestamp < since:
                continue
            if until and r.timestamp > until:
                continue
            result.append(r)
            if len(result) >= limit:
                break
        return list(reversed(result))

    def clear_history(self) -> None:
        """清空内存记录（不影响磁盘文件）。"""
        self._records.clear()

    def load_from_disk(self, date_str: str | None = None) -> int:
        """从磁盘加载指定日期的记录到内存。

        Args:
            date_str: 日期 YYYYMMDD，默认今天。

        Returns:
            加载的记录数。
        """
        if date_str is None:
            date_str = time.strftime("%Y%m%d")
        filename = f"{self._logs_dir}/sparrow_{date_str}.jsonl"
        if not os.path.exists(filename):
            return 0
        count = 0
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    self._records.append(
                        InspectionRecord(
                            timestamp=data["timestamp"],
                            kind=data["kind"],
                            level=data.get("level", ""),
                            content=data.get("content", ""),
                            snapshot=data.get("snapshot", {}),
                        )
                    )
                    count += 1
        except Exception as e:
            logger.warning("加载巡检历史失败: %s", e)
        return count

    # ============== 定时巡检 ==============

    async def run_light_inspection(self) -> InspectionRecord:
        """轻度简报巡检（5min）：仅汇总正常运行统计数据。"""
        snapshot = self._status.collect()
        brief = self._format_light_brief(snapshot)
        record = InspectionRecord(
            timestamp=time.time(),
            kind="light_brief",
            content=brief,
            snapshot={"agent_count": len(snapshot.agents)},
        )
        self._add_record(record)
        if self._broadcast:
            self._broadcast(brief)
        return record

    async def run_deep_inspection(self) -> InspectionRecord:
        """深度完整简报（30min）：导出 MD 报表存入 RAG。"""
        snapshot = self._status.collect()
        report_md = self._format_deep_report(snapshot)
        record = InspectionRecord(
            timestamp=time.time(),
            kind="deep_report",
            content=report_md,
            snapshot=snapshot.to_dict(),
        )
        self._add_record(record)
        # 联动 RAG：深度报表写入知识库供复盘
        if self._rag:
            try:
                self._rag.ingest(
                    id=f"sparrow_deep_{int(record.timestamp)}",
                    text=report_md,
                    metadata={
                        "kind": "deep_report",
                        "timestamp": record.timestamp,
                        "source": "sparrow_announcer",
                    },
                )
            except Exception as e:
                logger.warning("RAG 联动失败: %s", e)
        if self._broadcast:
            self._broadcast(report_md)
        return record

    async def start_periodic(self) -> None:
        """启动定时巡检循环。"""
        if self._running:
            return
        self._running = True
        self._light_task = asyncio.create_task(self._light_loop())
        self._deep_task = asyncio.create_task(self._deep_loop())
        logger.info(
            "灵音雀定时巡检已启动 (light=%ds, deep=%ds)",
            int(self._light_interval),
            int(self._deep_interval),
        )

    async def stop_periodic(self) -> None:
        """停止定时巡检。"""
        self._running = False
        if self._light_task:
            self._light_task.cancel()
            self._light_task = None
        if self._deep_task:
            self._deep_task.cancel()
            self._deep_task = None
        logger.info("灵音雀定时巡检已停止")

    async def _light_loop(self) -> None:
        """轻度巡检循环。"""
        while self._running:
            try:
                await asyncio.sleep(self._light_interval)
                await self.run_light_inspection()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("轻度巡检异常: %s", e)
                await asyncio.sleep(self._light_interval)

    async def _deep_loop(self) -> None:
        """深度巡检循环。"""
        while self._running:
            try:
                await asyncio.sleep(self._deep_interval)
                await self.run_deep_inspection()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("深度巡检异常: %s", e)
                await asyncio.sleep(self._deep_interval)

    def set_intervals(
        self, light: float | None = None, deep: float | None = None
    ) -> None:
        """调整巡检周期。"""
        if light is not None:
            self._light_interval = light
        if deep is not None:
            self._deep_interval = deep

    # ============== 异常告警 ==============

    def trigger_alert(
        self,
        level: AlertLevel,
        message: str,
        snapshot: SystemSnapshot | None = None,
    ) -> InspectionRecord:
        """触发告警推送（无需等待定时巡检）。

        Args:
            level: 告警等级。
            message: 告警消息。
            snapshot: 伴随快照（可选）。

        Returns:
            巡检记录。
        """
        prefix = {
            AlertLevel.LIGHT: "🟡 轻度告警",
            AlertLevel.MEDIUM: "🟠 中度告警",
            AlertLevel.HEAVY: "🔴 重度告警",
        }[level]
        content = f"{prefix}: {message}"
        record = InspectionRecord(
            timestamp=time.time(),
            kind="alert",
            level=level.value,
            content=content,
            snapshot=snapshot.to_dict() if snapshot else {},
        )
        self._add_record(record)
        # 告警强制推送（静默模式下也输出）
        if self._broadcast:
            self._broadcast(content, force=True)
        return record

    def check_and_alert(
        self, snapshot: SystemSnapshot | None = None
    ) -> list[InspectionRecord]:
        """根据快照自动检测并触发告警。

        Returns:
        触发的告警记录列表（可能为空）。
        """
        if snapshot is None:
            snapshot = self._status.collect()
        records: list[InspectionRecord] = []
        alerts = snapshot.alerts

        # 重度告警
        if alerts.secret_plaintext_risk:
            records.append(
                self.trigger_alert(
                    AlertLevel.HEAVY,
                    "密钥明文风险",
                    snapshot,
                )
            )
        if alerts.dependency_conflict:
            records.append(
                self.trigger_alert(
                    AlertLevel.HEAVY,
                    "依赖版本冲突",
                    snapshot,
                )
            )

        # 中度告警
        if alerts.nightmare_dream:
            records.append(
                self.trigger_alert(
                    AlertLevel.MEDIUM,
                    "噩梦级低质量梦境",
                    snapshot,
                )
            )
        # 测试连续失败检测（heal_progress 低 + 有 fix 记录）
        if (
            snapshot.security.heal_progress > 0
            and snapshot.security.heal_progress < 0.3
        ):
            records.append(
                self.trigger_alert(
                    AlertLevel.MEDIUM,
                    "测试连续失败，自愈进度低",
                    snapshot,
                )
            )

        # 轻度告警
        if alerts.token_overrun:
            records.append(
                self.trigger_alert(
                    AlertLevel.LIGHT,
                    "Token 消耗小幅超限",
                    snapshot,
                )
            )
        if alerts.memory_high:
            records.append(
                self.trigger_alert(
                    AlertLevel.LIGHT,
                    "内存占用过高",
                    snapshot,
                )
            )
        for agent_id in alerts.agent_stuck:
            records.append(
                self.trigger_alert(
                    AlertLevel.LIGHT,
                    f"员工 {agent_id} 长时间卡死",
                    snapshot,
                )
            )

        return records

    # ============== 节点播报 ==============

    def broadcast_node(self, node_type: str, **params: Any) -> InspectionRecord:
        """任务节点自动播报。

        Args:
            node_type: 节点类型，对应 _BROADCAST_TEMPLATES 的 key。
            **params: 模板参数。

        Returns:
            巡检记录。
        """
        # 优先查扩展模板，再查基础模板
        template = _BROADCAST_TEMPLATES_EXTENDED.get(
            node_type
        ) or _BROADCAST_TEMPLATES.get(node_type)
        if template is None:
            content = f"📌 {node_type}: {params}"
        else:
            try:
                content = template.format(**params)
            except (KeyError, IndexError):
                content = f"📌 {node_type}: {params}"
        record = InspectionRecord(
            timestamp=time.time(),
            kind="node_broadcast",
            content=content,
            snapshot={"node_type": node_type, "params": params},
        )
        self._add_record(record)
        if self._broadcast:
            self._broadcast(content)
        return record

    def list_node_types(self) -> list[str]:
        """列出所有支持的节点播报类型（基础 6 + 扩展 32 = 38 个）。"""
        return list(_BROADCAST_TEMPLATES.keys()) + list(
            _BROADCAST_TEMPLATES_EXTENDED.keys()
        )

    # ============== 简报格式化 ==============

    def _format_light_brief(self, snapshot: SystemSnapshot) -> str:
        """轻度简报格式化。"""
        lines = [
            f"【灵音雀轻度巡检 @ {time.strftime('%H:%M:%S', time.localtime(snapshot.collected_at))}】",
            (f"流水线: {snapshot.task_progress.active_pipelines} 激活 | "
            f"步骤: {snapshot.task_progress.completed_steps}/{snapshot.task_progress.total_steps}"),
            f"在岗员工: {len(snapshot.agents)} 名",
            f"高危拦截: {snapshot.system_runtime.hazardous_blocked_count} 次",
        ]
        # 预警简表
        alert_count = sum(
            [
                snapshot.alerts.token_overrun,
                snapshot.alerts.memory_high,
                snapshot.alerts.nightmare_dream,
                snapshot.alerts.secret_plaintext_risk,
                snapshot.alerts.dependency_conflict,
                bool(snapshot.alerts.agent_stuck),
            ]
        )
        lines.append(f"活跃预警: {alert_count} 项")
        return "\n".join(lines)

    # ============== 播报调度 ==============

    _schedule_id_counter: int = 0

    def schedule_broadcast(self, msg: str, t: float) -> int:
        """安排一条定时播报，t 为未来时间戳（秒）。返回 schedule id。"""
        self._schedule_id_counter += 1
        sid = self._schedule_id_counter
        delay = max(0.0, t - time.time())
        task = asyncio.ensure_future(self._delayed_broadcast(sid, msg, delay))
        if not hasattr(self, "_scheduled_tasks"):
            self._scheduled_tasks: dict[int, asyncio.Task] = {}
        self._scheduled_tasks[sid] = task
        return sid

    async def _delayed_broadcast(self, sid: int, msg: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if self._broadcast:
                self._broadcast(f"⏰ 定时播报: {msg}")
            self._add_record(
                InspectionRecord(
                    timestamp=time.time(),
                    kind="node_broadcast",
                    content=f"⏰ 定时播报: {msg}",
                )
            )
        except asyncio.CancelledError:
            logger.exception("Exception in block")

    def cancel_broadcast(self, sid: int) -> bool:
        """取消定时播报，返回是否成功取消。"""
        tasks = getattr(self, "_scheduled_tasks", {})
        task = tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
            return True
        return False

    # ============== 优先级队列播报 ==============

    _priority_queue: list[dict[str, Any]] = []

    def broadcast_priority(self, msg: str, priority: int = 0) -> None:
        """按优先级加入队列（priority 越高越优先）。"""
        self._priority_queue.append(
            {"msg": msg, "priority": priority, "ts": time.time()}
        )
        self._priority_queue.sort(key=lambda x: (-x["priority"], x["ts"]))

    def drain_priority_queue(self) -> list[str]:
        """取出并播报所有排队消息。"""
        output = []
        while self._priority_queue:
            item = self._priority_queue.pop(0)
            content = item["msg"]
            if self._broadcast:
                self._broadcast(content)
            output.append(content)
        return output

    def _format_deep_report(self, snapshot: SystemSnapshot) -> str:
        """深度完整报表（Markdown）。"""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snapshot.collected_at))
        lines = [
            f"# 灵音雀深度巡检报表 @ {ts}",
            "",
            "## 1. 全局任务进度",
            "",
            f"- 激活流水线: {snapshot.task_progress.active_pipelines}",
            f"- 步骤完成: {snapshot.task_progress.completed_steps}/{snapshot.task_progress.total_steps}",
            f"- 根需求: {snapshot.task_progress.root_demand or '(无)'}",
            f"- 关联员工: {', '.join(snapshot.task_progress.related_agents) or '(无)'}",
            f"- 梦境推演: {'开启' if snapshot.task_progress.dream_inference_enabled else '关闭'}",
            f"- 自动修复: {'触发' if snapshot.task_progress.auto_heal_triggered else '未触发'}",
            "",
            "## 2. 员工实时状态",
            "",
            "| Agent | 角色 | 状态 | 当前任务 | 积压 | 好感度 | 金币 | 报错 | 通过率 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for a in snapshot.agents:
            lines.append(
                f"| {a.agent_id} | {a.role} | {a.status} | {a.current_task or '-'} | "
                f"{a.backlog_count} | {a.affinity} | {a.coins} | {a.recent_errors} | "
                f"{a.pass_rate:.1%} |"
            )
        lines.extend(
            [
                "",
                "## 3. 底层系统运行",
                "",
                f"- 模型路由负载: {snapshot.system_runtime.router_load}",
                f"- Token 速率: {snapshot.system_runtime.token_rate}",
                f"- 上下文占用: {snapshot.system_runtime.context_occupancy:.1%}",
                f"- RAG 吞吐: {snapshot.system_runtime.rag_throughput}",
                f"- 梦境阶段: {snapshot.system_runtime.dream_stage_progress}",
                f"- MCP 调用频次: {snapshot.system_runtime.mcp_call_frequency}/s",
                f"- 高危拦截: {snapshot.system_runtime.hazardous_blocked_count}",
                "",
                "## 4. 风控 & 自动化流水线",
                "",
                f"- 漏洞拦截: {snapshot.security.blocked_threat_count}",
                f"- 自愈进度: {snapshot.security.heal_progress:.1%}",
                f"- 修复记录: {len(snapshot.security.fix_strategy_records)} 条",
                f"- Git 进度: {snapshot.security.github_push_progress or '(无)'}",
                "",
                "## 5. 预警提示",
                "",
            ]
        )
        if snapshot.alerts.token_overrun:
            lines.append("- 🔴 Token 超限")
        if snapshot.alerts.memory_high:
            lines.append("- 🟡 内存过高")
        if snapshot.alerts.agent_stuck:
            lines.append(f"- 🟡 员工卡死: {', '.join(snapshot.alerts.agent_stuck)}")
        if snapshot.alerts.nightmare_dream:
            lines.append("- 🟠 噩梦梦境")
        if snapshot.alerts.secret_plaintext_risk:
            lines.append("- 🔴 密钥明文风险")
        if snapshot.alerts.dependency_conflict:
            lines.append("- 🔴 依赖冲突")
        if not any(
            [
                snapshot.alerts.token_overrun,
                snapshot.alerts.memory_high,
                snapshot.alerts.agent_stuck,
                snapshot.alerts.nightmare_dream,
                snapshot.alerts.secret_plaintext_risk,
                snapshot.alerts.dependency_conflict,
            ]
        ):
            lines.append("- ✅ 无活跃预警")
        lines.extend(
            [
                "",
                "## 6. Git 流水线",
                "",
                f"- 分支: {snapshot.git.branch}",
                f"- 未提交文件: {snapshot.git.uncommitted_files}",
                f"- 最近提交: {snapshot.git.last_commit_hash} {snapshot.git.last_commit_message}",
                f"- 远程同步: {'是' if snapshot.git.remote_synced else '否'}",
                "",
                "## 7. 模型路由",
                "",
                f"- 任务类型: {', '.join(snapshot.router.task_types)}",
                f"- 模型分配: {snapshot.router.model_assignments}",
                f"- 降级模型: {', '.join(snapshot.router.degraded_models) or '(无)'}",
                f"- 失败计数: {snapshot.router.failure_counts}",
            ]
        )
        return "\n".join(lines)
