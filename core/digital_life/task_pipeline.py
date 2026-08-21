"""commit 37：多 Agent 协作流水线。

零基础读者可以这样理解：
- 复杂任务（如"写登录模块+测试+部署+扫描"）需要多个智能体配合
- 鹿（编排者）把任务拆成多个 step，每个 step 指定哪个智能体做、用什么工具
- 调度器按依赖关系自动跑：无依赖的并行，有依赖的等前面跑完
- 每个 step 在独立线程里跑，结果汇总成最终报告
- 失败的 step 不阻塞其他分支，但依赖它的 step 会被跳过

整体流程：
    用户自然语言输入
        ↓
    PipelineEngine.submit(task)
        ↓
    _decompose(task)  ← 用 LLM 拆解，失败时走预设模板
        ↓
    Pipeline(steps=[...])
        ↓
    调度器循环：扫描所有 step → 把就绪的派给对应 agent → 等结果
        ↓
    全部完成（或失败）后，鹿汇总报告
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from typing import Any

# ruff: noqa: F821
# ruff: noqa: S110, S112

# ----------------------------------------------------------------------
# 状态枚举（字符串，便于 JSON 序列化）
# ----------------------------------------------------------------------

STEP_PENDING = "pending"  # 等待前置
STEP_READY = "ready"  # 就绪可执行
STEP_RUNNING = "running"  # 执行中
STEP_DONE = "done"  # 成功
STEP_FAILED = "failed"  # 失败
STEP_SKIPPED = "skipped"  # 因前置失败被跳过
STEP_WAITING_APPROVAL = "waiting_approval"  # 等审批

PIPELINE_PENDING = "pending"
PIPELINE_RUNNING = "running"
PIPELINE_DONE = "done"
PIPELINE_FAILED = "failed"
PIPELINE_PARTIAL = "partial"  # 部分成功部分失败
PIPELINE_CANCELLED = "cancelled"


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------


class PipelineStep:
    """流水线中的一个步骤。

    零基础理解：流水线就是一张"工作分配表"，每一行就是一个 step。
    """

    __slots__ = (
        "agent_name_hint",
        "agent_species",
        "approval_id",
        "depends_on",
        "error",
        "finished_ts",
        "milestone_id",
        "order",
        # commit 39：关联项目 + 里程碑
        "project_id",
        "result",
        "started_ts",
        "status",
        "step_id",
        "task",
        "tool_calls",
        "tools",
    )

    def __init__(
        self,
        order: int,
        agent_species: str,
        task: str,
        tools: list[str] | None = None,
        depends_on: list[int] | None = None,
        agent_name_hint: str = "",
    ) -> None:
        self.step_id: int = order
        self.order: int = order
        self.agent_species: str = agent_species
        self.agent_name_hint: str = agent_name_hint
        self.task: str = task
        self.tools: list[str] = tools or []
        self.depends_on: list[int] = depends_on or []
        self.status: str = STEP_PENDING
        self.result: str = ""
        self.error: str = ""
        self.started_ts: float = 0
        self.finished_ts: float = 0
        self.tool_calls: list[dict] = []
        self.approval_id: int = 0
        # commit 39：关联项目 + 里程碑（可选，默认空）
        self.project_id: str = ""
        self.milestone_id: str = ""

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "order": self.order,
            "agent_species": self.agent_species,
            "agent_name_hint": self.agent_name_hint,
            "task": self.task,
            "tools": self.tools,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": self.result[:2000] if self.result else "",
            "error": self.error[:500] if self.error else "",
            "started_ts": self.started_ts,
            "finished_ts": self.finished_ts,
            "duration_sec": (
                round(self.finished_ts - self.started_ts, 2)
                if self.finished_ts and self.started_ts
                else 0
            ),
            "tool_calls": self.tool_calls,
            "project_id": self.project_id,
            "milestone_id": self.milestone_id,
        }


class Pipeline:
    """一条流水线。"""

    __slots__ = (
        "created_ts",
        "finished_ts",
        "id",
        "lock",
        "milestone_id",
        "name",
        "negotiation_log",
        "on_update",
        "original_task",
        # commit 39：关联项目
        "project_id",
        "retrospect",
        "status",
        "steps",
        "summary",
    )

    def __init__(
        self, name: str, original_task: str, steps: list[PipelineStep]
    ) -> None:
        self.id: str = uuid.uuid4().hex[:12]
        self.name: str = name
        self.original_task: str = original_task
        self.steps: list[PipelineStep] = steps
        self.status: str = PIPELINE_PENDING
        self.created_ts: float = time.time()
        self.finished_ts: float = 0
        self.summary: str = ""
        self.retrospect: dict = {}  # commit 38：流水线复盘
        self.negotiation_log: list = []  # commit 38：协商记录
        self.lock = threading.RLock()
        # 状态变更回调（前端轮询拿，也可以走回调推送）
        self.on_update = None  # callable(pipeline_id) -> None
        # commit 39：关联项目（可选）
        self.project_id: str = ""
        self.milestone_id: str = ""

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "name": self.name,
                "original_task": self.original_task,
                "status": self.status,
                "created_ts": self.created_ts,
                "finished_ts": self.finished_ts,
                "duration_sec": (
                    round(self.finished_ts - self.created_ts, 2)
                    if self.finished_ts
                    else 0
                ),
                "summary": self.summary,
                "steps": [s.to_dict() for s in self.steps],
                "retrospect": self.retrospect or {},
                "negotiation_log": list(self.negotiation_log or []),
                "project_id": self.project_id,
                "milestone_id": self.milestone_id,
            }

    def notify_update(self) -> None:
        if callable(self.on_update):
            try:
                self.on_update(self.id)
            except Exception:
                pass


# ----------------------------------------------------------------------
# 流水线引擎（单例）
# ----------------------------------------------------------------------


class PipelineEngine:
    """多 Agent 协作流水线调度引擎。

    单例。所有流水线都通过 submit() 提交到这里。
    """

    _instance: PipelineEngine | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pipelines: dict[str, Pipeline] = {}
        self._biosphere_ref: Any = None  # 由 Biosphere 启动时注入
        # 通知回调列表（监工可见的实时通知）
        self._notification_callbacks: list = []
        self._max_history = 50

    @classmethod
    def get_instance(cls) -> PipelineEngine:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_biosphere(self, biosphere: Any) -> None:
        """Biosphere 启动后调用此方法注入引用。"""
        self._biosphere_ref = biosphere

    def add_notification_callback(self, cb) -> None:
        """注册通知回调。cb(json_str) -> None。"""
        with self._lock:
            self._notification_callbacks.append(cb)

    def _notify(self, msg_type: str, content: dict) -> None:
        """向所有通知回调推一条消息。"""
        with self._lock:
            cbs = list(self._notification_callbacks)
        payload = {"type": msg_type, "ts": time.time(), **content}
        for cb in cbs:
            try:
                cb(payload)
            except Exception:
                pass

    # ---------------- 列表查询 ----------------

    def list_pipelines(self, limit: int = 20) -> list[dict]:
        with self._lock:
            items = sorted(
                self._pipelines.values(), key=lambda p: p.created_ts, reverse=True
            )[:limit]
            return [p.to_dict() for p in items]

    def get_pipeline(self, pid: str) -> dict | None:
        with self._lock:
            p = self._pipelines.get(pid)
            return p.to_dict() if p else None

    # ---------------- 提交流水线 ----------------

    def _create_pipeline(
        self,
        task: str,
        steps: list[PipelineStep],
        name: str,
        project_id: str,
        milestone_id: str,
    ) -> Pipeline:
        pipeline = Pipeline(name=name or task[:30], original_task=task, steps=steps)
        if project_id:
            pipeline.project_id = project_id
            if milestone_id:
                pipeline.milestone_id = milestone_id
            for s in pipeline.steps:
                s.project_id = project_id
                if milestone_id:
                    s.milestone_id = milestone_id
        return pipeline

    def _register_pipeline(self, pipeline: Pipeline) -> None:
        with self._lock:
            self._pipelines[pipeline.id] = pipeline
            if len(self._pipelines) > self._max_history:
                old = sorted(self._pipelines.values(), key=lambda p: p.created_ts)[
                    : len(self._pipelines) - self._max_history
                ]
                for p in old:
                    self._pipelines.pop(p.id, None)

    def _start_pipeline_execution(
        self, pipeline: Pipeline, steps: list[PipelineStep]
    ) -> None:
        pipeline.status = PIPELINE_RUNNING
        pipeline.notify_update()
        self._notify(
            "pipeline_started",
            {
                "pipeline_id": pipeline.id,
                "name": pipeline.name,
                "steps_count": len(steps),
                "project_id": pipeline.project_id,
                "milestone_id": pipeline.milestone_id,
            },
        )
        t = threading.Thread(
            target=self._run_pipeline,
            args=(pipeline,),
            daemon=True,
            name=f"pipeline-{pipeline.id}",
        )
        t.start()

    def submit(
        self, task: str, name: str = "", project_id: str = "", milestone_id: str = ""
    ) -> dict:
        """提交一个自然语言任务，自动拆解为流水线并启动执行。

        Args:
            task: 自然语言任务描述
            name: 流水线名（可选）
            project_id: commit 39 关联项目 ID（可选）
            milestone_id: commit 39 关联里程碑 ID（可选）

        返回：{"ok": bool, "pipeline_id": str, "steps_count": int, "error": str}
        """
        try:
            steps = self._decompose(task)
        except Exception as e:
            return {
                "ok": False,
                "pipeline_id": "",
                "steps_count": 0,
                "error": f"拆解失败: {e}",
            }
        if not steps:
            return {
                "ok": False,
                "pipeline_id": "",
                "steps_count": 0,
                "error": "拆解结果为空",
            }
        pipeline = self._create_pipeline(task, steps, name, project_id, milestone_id)
        self._register_pipeline(pipeline)
        self._start_pipeline_execution(pipeline, steps)
        return {
            "ok": True,
            "pipeline_id": pipeline.id,
            "steps_count": len(steps),
            "error": "",
        }

    # ---------------- 任务拆解 ----------------

    def _decompose(self, task: str) -> list[PipelineStep]:
        """用 LLM 把任务拆成多个 step。失败时走预设模板。"""
        router = self._get_router()
        if router is not None:
            try:
                steps = self._decompose_with_llm(router, task)
                if steps:
                    return steps
            except Exception:
                pass
        # 降级到规则拆解
        return self._decompose_with_rules(task)

    def _decompose_with_llm(self, router, task: str) -> list[PipelineStep]:
        """让 LLM 输出 JSON pipeline。"""
        prompt = self._build_decompose_prompt(task)
        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("loop closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            resp = loop.run_until_complete(
                router.complete_with_failover(
                    task_type="reasoning",
                    prompt=prompt,
                    agent_id="pipeline-decomposer",
                )
            )
            content = getattr(resp, "content", "") or ""
        except Exception:
            return []

        # 解析 JSON
        json_obj = self._extract_json(content)
        if not json_obj or "pipeline" not in json_obj:
            return []
        steps_data = json_obj["pipeline"]
        if not isinstance(steps_data, list):
            return []

        steps: list[PipelineStep] = []
        for s in steps_data:
            if not isinstance(s, dict):
                continue
            species = str(s.get("agent", "")).strip().lower()
            t = str(s.get("task", "")).strip()
            if not species or not t:
                continue
            tools = s.get("tools", []) or []
            if not isinstance(tools, list):
                tools = []
            deps = s.get("depends_on", []) or []
            if not isinstance(deps, list):
                deps = []
            try:
                step = PipelineStep(
                    order=int(s.get("step", len(steps) + 1)),
                    agent_species=species,
                    task=t,
                    tools=[str(x) for x in tools],
                    depends_on=[int(x) for x in deps],
                )
                steps.append(step)
            except Exception:
                continue
        # 按 order 排序，重置 step_id
        steps.sort(key=lambda x: x.order)
        for i, s in enumerate(steps, 1):
            s.step_id = i
            s.order = i
        return steps

    def _build_decompose_prompt(self, task: str) -> str:
        return f"""你是 BlueDeer 森林公司的任务编排鹿。请把下面的任务拆解成多步骤流水线。

可用物种代号：deer（编排）、squirrel（代码）、butterfly（UI）、fox（测试）、
hedgehog（安全）、beaver（运维）、raven（检索）、hare（统计）、
badger（网络）、lark（监控）、kite（调度）

要求：
1. 每个步骤只能交给上面列出的物种之一
2. depends_on 写前置步骤的 step 编号（数组）
3. 输出严格 JSON，不要带任何额外文字
4. 输出格式：
```json
{{
  "pipeline": [
    {{"step": 1, "agent": "squirrel", "task": "...", "tools": ["..."], "depends_on": []}},
    {{"step": 2, "agent": "fox", "task": "...", "tools": ["..."], "depends_on": [1]}}
  ]
}}
```

任务：{task}
"""

    def _extract_json(self, text: str) -> dict | None:
        """从 LLM 输出中提取 JSON 对象。"""
        # 优先 fenced code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 退而行内匹配
        m = re.search(r"\{[\s\S]*\"pipeline\"[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def _decompose_with_rules(self, task: str) -> list[PipelineStep]:
        """LLM 不可用时的规则拆解。

        简单粗暴：按关键词识别需要哪些物种，串成线性流水线。
        """
        from core.digital_life.agent_function_calling import route_task_to_species

        task_lower = task.lower()
        needed: list[tuple[str, str]] = []  # (species, sub_task)

        # 检测每个物种的关键词
        checks = [
            (
                "squirrel",
                [
                    "代码",
                    "实现",
                    "写一个",
                    "函数",
                    "code",
                    "python",
                    "补全",
                    "排序",
                    "查找",
                    "算法",
                ],
            ),
            ("butterfly", ["ui", "界面", "页面", "设计", "css", "html"]),
            ("fox", ["测试", "test", "fuzz", "覆盖", "用例"]),
            ("hedgehog", ["安全", "漏洞", "扫描", "vulnerability", "cipher"]),
            ("beaver", ["部署", "deploy", "文件", "存储", "kv", "事务"]),
            ("raven", ["检索", "rag", "向量", "搜索", "embedding"]),
            ("hare", ["统计", "分析", "回归", "分布", "异常"]),
            ("badger", ["http", "grpc", "dns", "网络", "接口"]),
            ("lark", ["监控", "告警", "metric", "dashboard"]),
            ("kite", ["调度", "拓扑", "规划", "schedule"]),
        ]
        for species, kws in checks:
            if any(kw in task_lower for kw in kws):
                needed.append((species, self._sub_task_for(species, task)))

        # 至少要有一个 step
        if not needed:
            # 没识别到具体物种，整体交给路由选出的物种
            sp = route_task_to_species(task)
            needed.append((sp, task))

        # 线性流水线：每步依赖前一步
        steps: list[PipelineStep] = []
        prev = 0
        for i, (sp, t) in enumerate(needed, 1):
            deps = [prev] if prev else []
            step = PipelineStep(
                order=i,
                agent_species=sp,
                task=t,
                tools=[],
                depends_on=deps,
            )
            steps.append(step)
            prev = i

        # 最后一步：鹿汇总
        steps.append(
            PipelineStep(
                order=len(steps) + 1,
                agent_species="deer",
                task=f"汇总所有步骤的结果，生成关于「{task[:60]}」的最终报告",
                tools=[],
                depends_on=[prev],
            )
        )
        return steps

    def _sub_task_for(self, species: str, original_task: str) -> str:
        """根据物种生成子任务描述。"""
        templates = {
            "squirrel": f"针对「{original_task[:60]}」编写相应的 Python 代码实现",
            "butterfly": f"针对「{original_task[:60]}」设计界面/UI 方案",
            "fox": f"针对「{original_task[:60]}」编写测试用例并执行",
            "hedgehog": f"针对「{original_task[:60]}」做安全扫描",
            "beaver": f"针对「{original_task[:60]}」执行部署/存储操作",
            "raven": f"针对「{original_task[:60]}」检索相关信息",
            "hare": f"针对「{original_task[:60]}」做数据统计分析",
            "badger": f"针对「{original_task[:60]}」处理网络请求相关操作",
            "lark": f"针对「{original_task[:60]}」做监控/告警检查",
            "kite": f"针对「{original_task[:60]}」做任务调度规划",
        }
        return templates.get(species, original_task)

    # ---------------- 调度执行 ----------------

    def _create_pipeline_executor(
        self, pipeline: Pipeline
    ) -> tuple[ThreadPoolExecutor, dict[int, Future]]:
        max_workers = min(8, max(2, len(pipeline.steps)))
        executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="pipe-step"
        )
        return executor, {}

    def _scan_ready_steps(self, pipeline: Pipeline) -> None:
        for step in pipeline.steps:
            if step.status != STEP_PENDING:
                continue
            deps_ok = True
            deps_failed = False
            for dep_id in step.depends_on:
                dep = next((x for x in pipeline.steps if x.step_id == dep_id), None)
                if dep is None:
                    continue
                if dep.status != STEP_DONE:
                    deps_ok = False
                    if dep.status in (STEP_FAILED, STEP_SKIPPED):
                        deps_failed = True
                    break
            if deps_failed:
                step.status = STEP_SKIPPED
                step.error = "前置步骤失败，跳过"
                step.finished_ts = time.time()
                self._notify(
                    "step_skipped",
                    {
                        "pipeline_id": pipeline.id,
                        "step_id": step.step_id,
                        "agent": step.agent_species,
                        "task": step.task[:80],
                    },
                )
                continue
            if deps_ok:
                step.status = STEP_READY

    def _dispatch_ready_steps(
        self,
        pipeline: Pipeline,
        executor: ThreadPoolExecutor,
        running: dict[int, Future],
    ) -> None:
        for step in pipeline.steps:
            if step.status == STEP_READY and step.step_id not in running:
                step.status = STEP_RUNNING
                step.started_ts = time.time()
                running[step.step_id] = executor.submit(
                    self._execute_step, pipeline, step
                )
                self._notify(
                    "step_started",
                    {
                        "pipeline_id": pipeline.id,
                        "step_id": step.step_id,
                        "agent": step.agent_species,
                        "task": step.task[:80],
                    },
                )

    def _collect_finished_steps(
        self, pipeline: Pipeline, running: dict[int, Future]
    ) -> None:
        done_ids = []
        for sid, fut in list(running.items()):
            if fut.done():
                done_ids.append(sid)
                del running[sid]
        if done_ids:
            pipeline.notify_update()

    def _finalize_pipeline(self, pipeline: Pipeline) -> None:
        done = sum(1 for s in pipeline.steps if s.status == STEP_DONE)
        failed = sum(
            1 for s in pipeline.steps if s.status in (STEP_FAILED, STEP_SKIPPED)
        )
        pipeline.finished_ts = time.time()
        if failed == 0:
            pipeline.status = PIPELINE_DONE
        elif done == 0:
            pipeline.status = PIPELINE_FAILED
        else:
            pipeline.status = PIPELINE_PARTIAL
        pipeline.summary = self._build_summary(pipeline)

    def _run_pipeline(self, pipeline: Pipeline) -> None:
        """后台线程：调度流水线执行。"""
        try:
            executor, running = self._create_pipeline_executor(pipeline)

            while True:
                with pipeline.lock:
                    pending = [
                        s
                        for s in pipeline.steps
                        if s.status in (STEP_PENDING, STEP_READY, STEP_RUNNING)
                    ]
                    if not pending:
                        break

                    self._scan_ready_steps(pipeline)
                    self._dispatch_ready_steps(pipeline, executor, running)

                self._collect_finished_steps(pipeline, running)
                time.sleep(0.2)

            executor.shutdown(wait=True)

            self._finalize_pipeline(pipeline)
            pipeline.notify_update()
            self._notify(
                "pipeline_finished",
                {
                    "pipeline_id": pipeline.id,
                    "status": pipeline.status,
                    "total": len(pipeline.steps),
                    "done": sum(1 for s in pipeline.steps if s.status == STEP_DONE),
                    "failed": sum(
                        1
                        for s in pipeline.steps
                        if s.status in (STEP_FAILED, STEP_SKIPPED)
                    ),
                    "summary": pipeline.summary[:200],
                },
            )

            if pipeline.project_id:
                try:
                    self._advance_milestone(
                        pipeline,
                        len(pipeline.steps),
                        sum(1 for s in pipeline.steps if s.status == STEP_DONE),
                        sum(
                            1
                            for s in pipeline.steps
                            if s.status in (STEP_FAILED, STEP_SKIPPED)
                        ),
                    )
                except Exception:
                    pass

            try:
                self._pipeline_retrospect(pipeline)
            except Exception:
                pass

        except Exception as e:
            with pipeline.lock:
                pipeline.status = PIPELINE_FAILED
                pipeline.summary = f"调度异常: {e}"
                pipeline.finished_ts = time.time()
            pipeline.notify_update()
            self._notify(
                "pipeline_failed",
                {
                    "pipeline_id": pipeline.id,
                    "error": str(e)[:200],
                },
            )

    # ---------------- 单步执行 ----------------

    def _negotiate_step(self, pipeline: Pipeline, step: PipelineStep) -> str:
        actual_species = step.agent_species
        candidates = [step.agent_species]
        try:
            from core.digital_life.negotiation_engine import get_negotiation_engine

            ne = get_negotiation_engine()
            if ne._biosphere_ref is None and self._biosphere_ref is not None:
                ne.set_biosphere(self._biosphere_ref)
            nego = ne.negotiate(
                pipeline_id=pipeline.id,
                step_id=step.step_id,
                task=step.task,
                candidate_species=candidates,
                timeout=2.0,
            )
            if nego.get("ok") and nego.get("winner"):
                actual_species = nego["winner"]
            with pipeline.lock:
                pipeline.negotiation_log.append(
                    {
                        "step_id": step.step_id,
                        "task": step.task[:80],
                        "candidates": candidates,
                        "winner": actual_species,
                        "bids": nego.get("bids", []),
                        "reason": nego.get("reason", ""),
                        "fallback": nego.get("fallback", False),
                        "ts": time.time(),
                    }
                )
        except Exception:
            pass
        return actual_species

    def _dispatch_step_to_agent(self, agent: Any, step: PipelineStep) -> dict:
        try:
            agent._tool_call_status = "running"
            agent._tool_call_meta = {
                "tool": step.tools[0] if step.tools else "",
                "task": step.task[:60],
                "step_id": step.step_id,
                "pipeline_id": step.pipeline_id,
            }
        except Exception:
            pass
        from core.digital_life.agent_function_calling import dispatch_task_to_agent

        return dispatch_task_to_agent(agent, step.task)

    def _update_step_result(
        self, pipeline: Pipeline, step: PipelineStep, agent: Any, result: dict
    ) -> None:
        with pipeline.lock:
            step.tool_calls = result.get("tool_calls", []) or []
            if result.get("ok"):
                step.status = STEP_DONE
                step.result = result.get("answer", "")[:3000]
                try:
                    agent._tool_call_status = "done"
                except Exception:
                    pass
            else:
                step.status = STEP_FAILED
                step.error = result.get("answer", "")[:500] or "unknown error"
                try:
                    agent._tool_call_status = "error"
                except Exception:
                    pass
            step.finished_ts = time.time()

    def _clear_agent_status(self, agent: Any, step: PipelineStep) -> None:
        time.sleep(1.5)
        try:
            if getattr(agent, "_tool_call_status", "") in ("done", "error"):
                meta = getattr(agent, "_tool_call_meta", {}) or {}
                if meta.get("step_id") == step.step_id:
                    agent._tool_call_status = ""
        except Exception:
            pass

    def _notify_step_finished(
        self, pipeline: Pipeline, step: PipelineStep, result: dict
    ) -> None:
        self._notify(
            "step_finished",
            {
                "pipeline_id": pipeline.id,
                "step_id": step.step_id,
                "agent": step.agent_species,
                "ok": result.get("ok", False),
                "result": (step.result if result.get("ok") else step.error)[:200],
            },
        )

    def _execute_step(self, pipeline: Pipeline, step: PipelineStep) -> None:
        """执行一个 step：找到对应物种的智能体，把任务派给它。"""
        try:
            actual_species = self._negotiate_step(pipeline, step)
            agent = self._find_agent(actual_species, step.agent_name_hint)
            if agent is None:
                with pipeline.lock:
                    step.status = STEP_FAILED
                    step.error = f"找不到物种 {actual_species} 的智能体"
                    step.finished_ts = time.time()
                return
            result = self._dispatch_step_to_agent(agent, step)
            self._update_step_result(pipeline, step, agent, result)
            threading.Thread(
                target=self._clear_agent_status, args=(agent, step), daemon=True
            ).start()
            self._notify_step_finished(pipeline, step, result)
        except Exception as e:
            with pipeline.lock:
                step.status = STEP_FAILED
                step.error = f"执行异常: {e}"
                step.finished_ts = time.time()
            self._notify(
                "step_failed",
                {
                    "pipeline_id": pipeline.id,
                    "step_id": step.step_id,
                    "error": str(e)[:200],
                },
            )

    # ---------------- 辅助 ----------------

    def _pipeline_retrospect(self, pipeline: Pipeline) -> None:
        """commit 38：流水线完成后触发整体复盘（由鹿汇总）。"""
        # 把每个 step 转成 tool_calls 格式
        tool_calls = []
        ok = True
        for s in pipeline.steps:
            tool_calls.append(
                {
                    "tool": f"step_{s.step_id}_{s.agent_species}",
                    "ok": s.status == STEP_DONE,
                    "result": {"output": s.result[:200] or s.error[:200]},
                }
            )
            if s.status != STEP_DONE:
                ok = False
        duration_sec = (pipeline.finished_ts or time.time()) - pipeline.created_ts
        try:
            from core.digital_life import retrospect

            router = self._get_router()
            retro = retrospect.generate_retrospect(
                agent_species="deer",
                agent_name="鹿·忧郁",
                task=f"流水线「{pipeline.name}」原始任务：{pipeline.original_task[:100]}",
                tool_calls=tool_calls,
                result_ok=ok,
                duration_sec=duration_sec,
                experience_adopted=[],
                router=router,
            )
            with pipeline.lock:
                pipeline.retrospect = retro
        except Exception:
            pass

    # ---------------- commit 39：项目里程碑联动 ----------------

    def _advance_milestone(
        self, pipeline: Pipeline, total: int, done: int, failed: int
    ) -> None:
        """流水线完成后，根据成败更新关联里程碑的进度。

        - 全部 step 成功 → 标记里程碑完成（进度 100%），自动通知下一里程碑启动
        - 部分成功 → 按完成率推进里程碑进度
        - 全部失败 → 里程碑进度不变，触发风险提醒
        """
        from core.digital_life.project_manager import get_project_manager

        mgr = get_project_manager()
        if not pipeline.project_id:
            return
        proj_obj = mgr._get_project_obj(pipeline.project_id)
        if proj_obj is None:
            return

        # 计算进度增量
        if total <= 0:
            return
        success_ratio = done / total
        if pipeline.milestone_id:
            # 找到对应里程碑
            milestone = None
            for m in proj_obj.milestones:
                if m.id == pipeline.milestone_id:
                    milestone = m
                    break
            if milestone is None:
                return
            old_progress = milestone.progress
            # 全部成功 → 完成
            if failed == 0 and done > 0:
                new_progress = 100
                new_status = "done"
                mgr.update_milestone_progress(
                    pipeline.project_id,
                    pipeline.milestone_id,
                    progress=100,
                    status="done",
                )
            else:
                # 部分成功 → 推进进度（按完成率）
                new_progress = min(99, int(old_progress + success_ratio * 50))
                new_status = "in_progress"
                mgr.update_milestone_progress(
                    pipeline.project_id,
                    pipeline.milestone_id,
                    progress=new_progress,
                    status="in_progress",
                )

            # 累加参与 agent 的项目贡献统计
            self._record_project_contributions(pipeline, proj_obj)

            # 通知监工
            self._notify(
                "milestone_progress",
                {
                    "pipeline_id": pipeline.id,
                    "project_id": pipeline.project_id,
                    "milestone_id": pipeline.milestone_id,
                    "milestone_name": milestone.name,
                    "old_progress": old_progress,
                    "new_progress": new_progress,
                    "status": new_status,
                    "ok": failed == 0,
                },
            )

            # 如果里程碑完成，自动触发下一里程碑
            if new_status == "done":
                self._trigger_next_milestone(proj_obj, milestone)
        else:
            # 没指定 milestone_id，只是项目级贡献
            self._record_project_contributions(pipeline, proj_obj)

    def _record_project_contributions(self, pipeline: Pipeline, project) -> None:
        """累加每个参与 step 的智能体在该项目上的贡献统计。"""
        if self._biosphere_ref is None:
            return
        try:
            employees = getattr(self._biosphere_ref, "employees", []) or []
            for step in pipeline.steps:
                if step.status != STEP_DONE:
                    continue
                # 找到执行该 step 的智能体
                for lf in employees:
                    if getattr(lf, "species", "") == step.agent_species and getattr(
                        lf, "_alive", False
                    ):
                        contrib = getattr(lf, "project_contributions", None) or {}
                        c = dict(contrib.get(pipeline.project_id, {}))
                        c["tasks"] = int(c.get("tasks", 0)) + 1
                        c["commits"] = int(c.get("commits", 0)) + 1
                        c["last_active_ts"] = time.time()
                        c["role"] = c.get("role", step.agent_species)
                        # 写回（避免 __slots__ 限制）
                        try:
                            lf.project_contributions = {
                                **contrib,
                                pipeline.project_id: c,
                            }
                        except Exception:
                            pass
                        # 累加工作产出
                        try:
                            lf._work_output = (
                                float(getattr(lf, "_work_output", 0.0)) + 1.0
                            )
                        except Exception:
                            pass
                        break  # 每物种一只，找到就 break
        except Exception:
            pass

    def _trigger_next_milestone(self, project, finished_milestone) -> None:
        """里程碑完成后自动启动下一里程碑（依赖关系判定）。"""
        from core.digital_life.project_manager import get_project_manager

        mgr = get_project_manager()
        # 找到所有依赖刚完成里程碑的、尚未开始的里程碑
        triggered: list[str] = []
        for m in project.milestones:
            if m.status != "pending":
                continue
            if finished_milestone.id in (m.depends_on or []):
                mgr.update_milestone_progress(
                    project.id,
                    m.id,
                    progress=0,
                    status="in_progress",
                )
                triggered.append(m.name)
        if triggered:
            self._notify(
                "milestone_auto_started",
                {
                    "project_id": project.id,
                    "project_name": project.name,
                    "finished_milestone": finished_milestone.name,
                    "next_milestones": triggered,
                },
            )

    def _get_router(self):
        if self._biosphere_ref is None:
            return None
        return getattr(self._biosphere_ref, "_router", None)

    def _find_agent(self, species: str, name_hint: str = "") -> Any:
        """从 biosphere 里找一个指定物种的活着的智能体。"""
        if self._biosphere_ref is None:
            return None
        # 优先按 name_hint
        try:
            # biosphere.employees 是 list[DigitalLifeForm]
            employees = (
                getattr(self._biosphere_ref, "employees", None)
                or getattr(self._biosphere_ref, "env", None)
                and getattr(self._biosphere_ref.env, "population", None)
                or []
            )
            # 优先匹配名字
            if name_hint:
                for a in employees:
                    if (
                        getattr(a, "species", "") == species
                        and getattr(a, "_name_obj", "") == name_hint
                        and getattr(a, "_alive", False)
                    ):
                        return a
            # 任意该物种的活体
            for a in employees:
                if getattr(a, "species", "") == species and getattr(a, "_alive", False):
                    return a
        except Exception:
            pass
        return None

    def _build_summary(self, pipeline: Pipeline) -> str:
        """生成流水线最终汇总报告。"""
        lines: list[str] = []
        lines.append(f"流水线「{pipeline.name}」执行完毕")
        lines.append(
            f"总步骤: {len(pipeline.steps)}，"
            f"成功: {sum(1 for s in pipeline.steps if s.status == STEP_DONE)}，"
            f"失败: {sum(1 for s in pipeline.steps if s.status == STEP_FAILED)}，"
            f"跳过: {sum(1 for s in pipeline.steps if s.status == STEP_SKIPPED)}"
        )
        lines.append("")
        lines.append("各步骤结果：")
        for s in pipeline.steps:
            status_icon = {
                STEP_DONE: "[OK]",
                STEP_FAILED: "[FAIL]",
                STEP_SKIPPED: "[SKIP]",
                STEP_RUNNING: "[RUN]",
                STEP_PENDING: "[WAIT]",
                STEP_READY: "[RDY]",
            }.get(s.status, "[?]")
            result_preview = (s.result if s.status == STEP_DONE else s.error)[:100]
            lines.append(
                f"  {status_icon} step{s.step_id} [{s.agent_species}]: {result_preview}"
            )
        return "\n".join(lines)

    # ---------------- 控制 ----------------

    def cancel_pipeline(self, pid: str) -> bool:
        """取消流水线（标记 pending/ready 步骤为 skipped）。"""
        with self._lock:
            p = self._pipelines.get(pid)
        if p is None:
            return False
        with p.lock:
            if p.status in (
                PIPELINE_DONE,
                PIPELINE_FAILED,
                PIPELINE_PARTIAL,
                PIPELINE_CANCELLED,
            ):
                return False
            for s in p.steps:
                if s.status in (STEP_PENDING, STEP_READY):
                    s.status = STEP_SKIPPED
                    s.error = "pipeline cancelled"
                    s.finished_ts = time.time()
            p.status = PIPELINE_CANCELLED
            p.finished_ts = time.time()
        p.notify_update()
        self._notify("pipeline_cancelled", {"pipeline_id": pid})
        return True


def get_pipeline_engine() -> PipelineEngine:
    return PipelineEngine.get_instance()


# ----------------------------------------------------------------------
# 单智能体直接执行（不走流水线）
# ----------------------------------------------------------------------


class PipelineResult:
    __slots__ = (
        "created_ts",
        "duration_sec",
        "finished_ts",
        "pipeline_id",
        "status",
        "steps",
        "summary",
    )

    def __init__(
        self, pipeline_id, status, steps, summary, duration_sec, created_ts, finished_ts
    ):
        self.pipeline_id = pipeline_id
        self.status = status
        self.steps = steps
        self.summary = summary
        self.duration_sec = duration_sec
        self.created_ts = created_ts
        self.finished_ts = finished_ts

    def to_dict(self):
        return {s: getattr(self, s) for s in self.__slots__}

    @classmethod
    def from_pipeline(cls, p: Pipeline):
        return cls(
            pipeline_id=p.id,
            status=p.status,
            steps=[s.to_dict() for s in p.steps],
            summary=p.summary,
            duration_sec=(p.finished_ts - p.created_ts) if p.finished_ts else 0,
            created_ts=p.created_ts,
            finished_ts=p.finished_ts,
        )


def run_pipeline(
    task: str, name: str = "", project_id: str = "", milestone_id: str = ""
) -> PipelineResult:
    eng = get_pipeline_engine()
    result = eng.submit(
        task, name=name, project_id=project_id, milestone_id=milestone_id
    )
    if not result["ok"]:
        return PipelineResult("", PIPELINE_FAILED, [], result.get("error", ""), 0, 0, 0)
    pid = result["pipeline_id"]
    p = eng._pipelines.get(pid)
    ev = threading.Event()

    def _on_done(_pid=None):
        ev.set()

    if p:
        p.on_update = _on_done
    ev.wait(timeout=300)
    p = eng._pipelines.get(pid)
    if p is None:
        return PipelineResult(pid, PIPELINE_FAILED, [], "pipeline lost", 0, 0, 0)
    return PipelineResult.from_pipeline(p)


def retry_failed(pipeline_id: str) -> PipelineResult:
    eng = get_pipeline_engine()
    p = eng._pipelines.get(pipeline_id)
    if p is None:
        return PipelineResult("", PIPELINE_FAILED, [], "pipeline not found", 0, 0, 0)
    with p.lock:
        for s in p.steps:
            if s.status in (STEP_FAILED, STEP_SKIPPED):
                s.status = STEP_PENDING
                s.started_ts = 0
                s.finished_ts = 0
                s.result = ""
                s.error = ""
        p.status = PIPELINE_RUNNING
        p.finished_ts = 0
        p.summary = ""
    ev = threading.Event()

    def _on_done(_pid=None):
        ev.set()

    p.on_update = _on_done
    t = threading.Thread(
        target=eng._run_pipeline, args=(p,), daemon=True, name=f"retry-{p.id}"
    )
    t.start()
    ev.wait(timeout=300)
    p = eng._pipelines.get(pipeline_id)
    if p is None:
        return PipelineResult(
            pipeline_id, PIPELINE_FAILED, [], "pipeline lost", 0, 0, 0
        )
    return PipelineResult.from_pipeline(p)


def run_single_agent_task(species: str, task: str, environment=None) -> dict:
    """直接派给单个物种的智能体执行（不走流水线）。

    返回：
        {"ok": bool, "agent": str, "answer": str, "tool_calls": list, "rounds": int}
    """
    from core.digital_life.agent_function_calling import (
        dispatch_task_to_agent,
        find_agent_by_species,
    )

    agent = find_agent_by_species(species, environment)
    if agent is None:
        return {
            "ok": False,
            "agent": species,
            "answer": "",
            "error": f"找不到 {species} 物种的智能体",
            "tool_calls": [],
            "rounds": 0,
        }

    result = dispatch_task_to_agent(agent, task)
    result["agent"] = species
    return result
