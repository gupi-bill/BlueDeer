"""commit 37：LLM Function Calling 封装。

零基础读者可以这样理解：
- 智能体接到任务后，需要"思考"用哪个工具、参数填什么
- 这件事交给 LLM 来做：把任务描述 + 工具清单丢给 LLM
- LLM 返回"我要调用 XXX 工具，参数是 YYY"
- 我们真的执行这个工具，把结果再丢回给 LLM
- LLM 看到结果后，要么继续调下一个工具，要么说"我做完了"

设计要点：
1. 零第三方依赖：用 Router.complete_with_failover() 调 LLM
2. 不破坏现有系统：完全独立模块
3. 多轮工具调用：最多 5 轮，防止死循环
4. 失败降级：LLM 不可用时，按"关键词匹配"挑工具
5. 工具调用结果自动写入智能体短期记忆
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from typing import Any

# 单轮工具调用的最大轮数（防止 LLM 死循环）
MAX_TOOL_ROUNDS = 5

# 物种擅长领域的关键词映射（用于 LLM 不可用时的降级路由）
SPECIES_KEYWORDS: dict[str, list[str]] = {
    "squirrel": ["代码", "函数", "实现", "补全", "code", "python", "写一个",
                  "排序", "查找", "算法", "树"],
    "butterfly": ["ui", "界面", "页面", "设计", "颜色", "布局", "图标",
                   "css", "html", "样式"],
    "fox": ["测试", "fuzz", "覆盖", "用例", "bug", "review", "审计",
             "test", "hypothesis"],
    "hedgehog": ["安全", "漏洞", "加密", "证书", "扫描", "sandbox",
                  "cipher", "vulnerability", "security"],
    "beaver": ["文件", "存储", "部署", "事务", "txn", "kv", "bitcask",
                "lsm", "mvcc", "buffer"],
    "raven": ["检索", "向量", "索引", "rag", "embedding", "搜索",
               "inverted", "recall"],
    "hare": ["统计", "回归", "分布", "均值", "方差", "异常", "bootstrap",
              "stats", "regression", "t-digest"],
    "badger": ["http", "grpc", "dns", "websocket", "mq", "网络",
                "请求", "接口"],
    "lark": ["监控", "告警", "metric", "仪表盘", "日志", "dashboard",
              "alert", "log"],
    "kite": ["调度", "拓扑", "约束", "规划", "critical", "path",
              "schedule", "csp", "linear"],
    "deer": ["编排", "拆解", "汇总", "协调", "consensus", "event",
              "pipeline", "orchestrate"],
}


# ----------------------------------------------------------------------
# LLM Prompt
# ----------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """你是 BlueDeer 森林公司的{role_name}（{species_zh}）。
你擅长以下工具：
{tool_list}

当用户给你一个任务时，你需要：
1. 判断是否需要调用工具
2. 如果需要，输出 JSON 调用工具，格式如下：
```tool
{"tool": "工具名", "params": {"参数名": "值}}
```
3. 一次只调用一个工具，看到结果后再决定下一步
4. 任务完成后，直接给出最终答复（不要调工具）

注意：
- 工具名必须从上面列表中选
- 参数必须严格按照工具的参数定义填
- 如果任务不需要工具，直接回答用户
- 不要编造结果，工具调用结果以实际返回为准
"""


# ----------------------------------------------------------------------
# 核心：Function Calling 封装
# ----------------------------------------------------------------------

class FunctionCaller:
    """LLM Function Calling 封装（每个智能体一个实例）。

    用法：
        fc = FunctionCaller(agent)
        result = fc.run_task("写一个快速排序的 Python 实现")
        # result = {"ok": True, "answer": "...", "tool_calls": [...], "rounds": 2}
    """

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.species: str = getattr(agent, "species", "") or ""
        self.agent_name: str = getattr(agent, "_name_obj", "") or ""
        self.agent_id: str = ""
        try:
            self.agent_id = agent.get_agent_id()
        except Exception:
            self.agent_id = self.species + "-" + self.agent_name

        # 懒加载
        from core.digital_life.tool_registry import get_tool_registry
        self._registry = get_tool_registry()
        from core.digital_life.tool_executor import get_tool_executor
        self._executor = get_tool_executor()

        # 物种中文名（用于 prompt）
        self.species_zh = _SPECIES_ZH.get(self.species, self.species)
        # 角色定位（用于 prompt）
        self.role_name = _SPECIES_ROLE.get(self.species, "员工")

        # 本物种可用工具
        self.bound_tools: list[str] = self._registry.list_tool_names_for_species(
            self.species) if self.species else []

    # ---------------- 主入口 ----------------

    def run_task(self, task: str, max_rounds: int = MAX_TOOL_ROUNDS,
                 enable_retrospect: bool = True) -> dict:
        """执行一个任务，可能多轮调用工具。

        返回：
            {
                "ok": bool,
                "answer": str,           # 最终答复
                "tool_calls": list[dict], # 工具调用记录
                "rounds": int,            # 总轮数
                "fallback": bool,         # 是否走了降级路径
                "retrospect": dict,       # commit 38：复盘记录
                "adopted_experiences": list,  # 本次采用的经验
            }
        """
        # commit 38：执行前检索相关经验
        adopted_exp_ids: list[str] = []
        adopted_exp_strs: list[str] = []
        try:
            from core.digital_life.experience_library import (
                get_experience_library,
            )
            lib = get_experience_library()
            experiences = lib.search_by_task(task, agent_species=self.species,
                                              limit=3)
            if experiences:
                adopted_exp_strs = [
                    f"[{e.get('task_type','')}] {e.get('lesson','')}"
                    for e in experiences
                ]
                adopted_exp_ids = [e.get("id", "") for e in experiences
                                    if e.get("id")]
        except Exception:
            pass

        start_ts = time.time()
        result: dict
        # 路径 1：尝试 LLM 路由
        try:
            result = self._run_with_llm(
                task, max_rounds, adopted_exp_strs=adopted_exp_strs)
        except Exception as e:
            # 路径 2：降级到关键词路由
            result = self._run_fallback(
                task, str(e), adopted_exp_strs=adopted_exp_strs)
        duration_sec = time.time() - start_ts

        # commit 38：执行后触发复盘
        retro: dict = {}
        if enable_retrospect:
            try:
                from core.digital_life import retrospect
                router = self._get_router()
                retro = retrospect.generate_retrospect(
                    agent_species=self.species,
                    agent_name=self.agent_name,
                    task=task,
                    tool_calls=result.get("tool_calls", []),
                    result_ok=bool(result.get("ok")),
                    duration_sec=duration_sec,
                    experience_adopted=adopted_exp_strs,
                    router=router,
                )
                # 更新经验权重（采用过的经验）
                if adopted_exp_ids and retro.get("lesson"):
                    better = retrospect.evaluate_experience_outcome(
                        prev_ok_rate=0.7,
                        current_ok=bool(result.get("ok")),
                    )
                    for eid in adopted_exp_ids:
                        try:
                            from core.digital_life.experience_library import (
                                get_experience_library,
                            )
                            get_experience_library().adopt_experience(
                                eid, self.species, better)
                        except Exception:
                            pass
            except Exception:
                pass

        result["retrospect"] = retro
        result["adopted_experiences"] = adopted_exp_strs
        return result

    # ---------------- LLM 路径 ----------------

    def _run_with_llm(self, task: str, max_rounds: int,
                       adopted_exp_strs: list = None) -> dict:
        router = self._get_router()
        if router is None:
            raise RuntimeError("no llm router available")

        tool_list_str = self._format_tool_list()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role_name=self.role_name,
            species_zh=self.species_zh,
            tool_list=tool_list_str,
        )

        # commit 38：把历史经验注入 user prompt
        user_content = task
        if adopted_exp_strs:
            exp_block = "\n\n【历史经验】\n" + "\n".join(
                f"- {s}" for s in adopted_exp_strs)
            user_content = task + exp_block

        # 多轮对话历史
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        tool_calls: list[dict] = []

        for round_idx in range(1, max_rounds + 1):
            # 把 messages 拼成单个 prompt（我们的 LLM 接口是单 prompt 的）
            prompt = self._messages_to_prompt(messages)
            response = self._call_llm(router, prompt)
            assistant_text = response or ""
            messages.append({"role": "assistant", "content": assistant_text})

            # 解析是否要调工具
            tool_call = self._parse_tool_call(assistant_text)
            if tool_call is None:
                # 不调工具，任务结束
                return {
                    "ok": True,
                    "answer": assistant_text.strip(),
                    "tool_calls": tool_calls,
                    "rounds": round_idx,
                    "fallback": False,
                }

            # 执行工具
            tool_name = tool_call.get("tool", "")
            params = tool_call.get("params", {}) or {}
            if not isinstance(params, dict):
                params = {}

            # 校验工具是否在白名单
            if tool_name not in self.bound_tools:
                tool_result_str = f"错误：工具 {tool_name} 不在你的可用工具列表中。"
            else:
                result = self._executor.execute(self.agent, tool_name, params)
                tool_calls.append({
                    "round": round_idx,
                    "tool": tool_name,
                    "params": params,
                    "result": result.to_dict(),
                })
                # 写入智能体短期记忆
                self._memorize_tool_call(tool_name, params, result)
                tool_result_str = self._format_tool_result(result)

            messages.append({"role": "user", "content": "工具结果：\n" + tool_result_str})

        # 达到最大轮数仍未完成
        return {
            "ok": False,
            "answer": "达到最大工具调用轮数仍未完成",
            "tool_calls": tool_calls,
            "rounds": max_rounds,
            "fallback": False,
        }

    # ---------------- 降级路径（LLM 不可用时） ----------------

    def _run_fallback(self, task: str, reason: str,
                       adopted_exp_strs: list = None) -> dict:
        """LLM 不可用时，按关键词匹配挑一个工具调用一次。"""
        tool_calls: list[dict] = []
        answer_parts: list[str] = [f"（LLM 不可用，走降级路由：{reason}）"]

        # commit 38：把采用的经验写入答复
        if adopted_exp_strs:
            answer_parts.append("参考历史经验：")
            for e in adopted_exp_strs:
                answer_parts.append(f"  - {e}")

        # 在本物种工具中找最匹配的（按得分排序）
        candidates: list[tuple[int, str, dict]] = []
        for tool_name in self.bound_tools:
            tool_desc = self._registry.get_tool(tool_name)
            if tool_desc is None:
                continue
            score = self._score_tool_match(task, tool_name, tool_desc)
            if score > 0:
                candidates.append((score, tool_name, tool_desc))
        candidates.sort(key=lambda x: x[0], reverse=True)

        if not candidates:
            return {
                "ok": False,
                "answer": "无法处理此任务（LLM 不可用且无工具匹配）：" + reason,
                "tool_calls": [],
                "rounds": 0,
                "fallback": True,
            }

        picked = candidates[0][1]
        picked_desc = candidates[0][2]

        # 构造调用参数：从 task 文本里抽取关键信息 + 用工具默认值兜底
        params = self._build_fallback_params(picked, picked_desc, task)
        result = self._executor.execute(self.agent, picked, params)
        tool_calls.append({
            "round": 1,
            "tool": picked,
            "params": params,
            "result": result.to_dict(),
        })
        self._memorize_tool_call(picked, params, result)

        if result.ok:
            answer_parts.append(f"调用 {picked} 成功：\n{result.output}")
        else:
            answer_parts.append(f"调用 {picked} 失败：{result.error}")

        return {
            "ok": result.ok,
            "answer": "\n".join(answer_parts),
            "tool_calls": tool_calls,
            "rounds": 1,
            "fallback": True,
        }

    def _score_tool_match(self, task: str, tool_name: str,
                            tool_desc: dict) -> int:
        """给任务-工具匹配打分。0 表示不匹配。"""
        # LLM 不可用时，必须用有真实实现的工具（fallback 或真实模块）
        # 没有 fallback 的工具直接 0 分（避免选到无法执行的工具）
        from core.digital_life.tool_registry import FALLBACK_IMPLEMENTATIONS
        has_impl = (
            tool_name in FALLBACK_IMPLEMENTATIONS
            or bool(tool_desc.get("module_path"))
        )
        if not has_impl:
            return 0
        task_lower = task.lower()
        # 工具描述池：工具名 + description + 模块路径
        pool = (
            tool_name + " " +
            tool_desc.get("description", "") + " " +
            tool_desc.get("module_path", "")
        ).lower()
        score = 0
        # 1. 工具名直接出现在任务里（最高分）
        if tool_name.lower() in task_lower:
            score += 50
        # 2. 任务中的词（按空格/标点切分）出现在描述池里
        for kw in re.split(r"[\s,，。、「」\'\"]+", task_lower):
            kw = kw.strip()
            if len(kw) >= 2 and kw in pool:
                score += 10
        # 3. 任务中的 2-gram 子串出现在描述池里（覆盖"代码实现"→"代码"）
        # 同时考虑工具描述的关键词出现在任务里
        for kw in re.split(r"[\s,，。、]+", pool):
            kw = kw.strip()
            if 2 <= len(kw) <= 8 and kw in task_lower:
                score += 5
        # 4. SPECIES_KEYWORDS 加权（物种擅长领域命中工具描述）
        species_kws = SPECIES_KEYWORDS.get(self.agent.species, [])
        for kw in species_kws:
            if kw.lower() in task_lower and kw.lower() in pool:
                score += 3
        return score

    def _build_fallback_params(self, tool_name: str, tool_desc: dict,
                                 task: str) -> dict:
        """从任务文本里抽参 + 用工具参数默认值兜底。

        优先级：
        1. 工具描述里有默认值 → 用默认值
        2. 按参数名做语义抽取（prefix→代码片段、language→编程语言、name→名词...）
        3. 按 type 兜底（str=任务文本、int=第一个数字、float=第一个浮点...）
        """
        params: dict = {}
        param_specs = tool_desc.get("parameters", {}) or {}
        for pname, pspec in param_specs.items():
            if not isinstance(pspec, dict):
                continue
            ptype = str(pspec.get("type", "str")).lower()
            # 默认值
            default = pspec.get("default")
            if default is not None:
                params[pname] = default
                continue
            # 先按参数名做语义抽取
            v = self._extract_by_name(pname, task)
            if v is not None:
                params[pname] = v
                continue
            # 按 type 兜底
            if ptype in ("str", "string", "any"):
                params[pname] = task[:200]
            elif ptype in ("int", "integer"):
                m = re.search(r"\d+", task)
                params[pname] = int(m.group(0)) if m else 10
            elif ptype in ("float", "number"):
                m = re.search(r"\d+\.?\d*", task)
                params[pname] = float(m.group(0)) if m else 1.0
            elif ptype in ("list", "array"):
                params[pname] = []
            elif ptype in ("dict", "object"):
                params[pname] = {}
            elif ptype in ("bool", "boolean"):
                params[pname] = False
        return params

    def _extract_by_name(self, pname: str, task: str) -> Any:
        """按参数名做语义抽取，返回 None 表示没匹配到。"""
        n = pname.lower()
        # 代码前缀：从 "前缀 XXX" 或代码标识符中抽
        if "prefix" in n or "code" in n:
            m = re.search(r"前缀\s*[\"'`]?(.+?)[\"'`]?\s*$", task)
            if m:
                return m.group(1).strip()
            # 找任务中形如 def xxx / class xxx / func xxx 的代码片段
            m = re.search(r"((?:def|class|func|fn|function|public|private|void)\s+\w+.*?)(?:[\s。，,]|$)", task)
            if m:
                return m.group(1).strip()
            # 找引号里的代码
            m = re.search(r"[\"'`]([^\"'`]{2,80})[\"'`]", task)
            if m and re.search(r"[a-zA-Z_]", m.group(1)):
                return m.group(1)
            return None
        # 编程语言
        if "language" in n or "lang" in n:
            for lang in ("python", "java", "javascript", "js", "go",
                         "rust", "c++", "cpp", "ruby", "php", "kotlin",
                         "swift", "typescript", "ts"):
                if re.search(rf"\b{re.escape(lang)}\b", task, re.IGNORECASE):
                    return "javascript" if lang.lower() == "js" else (
                        "typescript" if lang.lower() == "ts" else
                        "cpp" if lang.lower() in ("c++", "cpp") else lang.lower())
            return None
        # 名称：从 "叫 XXX" / "名为 XXX" / "name XXX" 抽
        if "name" in n and "user" not in n:
            m = re.search(r"(?:叫|名为|名字|name[：:\s]+)([A-Za-z_][\w\u4e00-\u9fa5]{1,40})", task)
            if m:
                return m.group(1)
            return None
        # 路径 / 文件
        if "path" in n or "file" in n:
            m = re.search(r"([\w./\\-]+\.\w+)", task)
            if m:
                return m.group(1)
            return None
        return None

    # ---------------- 辅助 ----------------

    def _get_router(self):
        env = getattr(self.agent, "_environment", None)
        if env is None:
            return None
        biosphere = getattr(env, "_biosphere_ref", None)
        if biosphere is None:
            return None
        return getattr(biosphere, "_router", None)

    def _call_llm(self, router, prompt: str) -> str:
        """调用 LLM。我们的 Router 是 async 的，需要在事件循环里跑。"""
        try:
            # 复用现有事件循环或新建
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("loop closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                # 我们已经在事件循环里（不应该发生，但兜底）
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        lambda: asyncio.run(router.complete_with_failover(
                            task_type="reasoning",
                            prompt=prompt,
                            agent_id=self.agent_id,
                        )))
                    resp = future.result(timeout=60)
            else:
                resp = loop.run_until_complete(
                    router.complete_with_failover(
                        task_type="reasoning",
                        prompt=prompt,
                        agent_id=self.agent_id,
                    )
                )
            return getattr(resp, "content", "") or ""
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def _messages_to_prompt(self, messages: list[dict]) -> str:
        """把多轮对话历史拼成单个 prompt。"""
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append("[系统]\n" + content)
            elif role == "assistant":
                parts.append("[助手]\n" + content)
            else:
                parts.append("[用户]\n" + content)
        parts.append("[助手]\n")
        return "\n\n".join(parts)

    def _format_tool_list(self) -> str:
        lines: list[str] = []
        for name in self.bound_tools:
            desc = self._registry.get_tool(name)
            if desc is None:
                continue
            params = desc.get("parameters", {}) or {}
            param_str = ", ".join(
                f"{k}: {v.get('type', 'any')}" for k, v in params.items()
            )
            lines.append(f"- {name}({param_str}): {desc.get('description', '')[:80]}")
        return "\n".join(lines) if lines else "（无可用工具）"

    def _parse_tool_call(self, text: str) -> dict | None:
        """从 LLM 输出中解析工具调用。

        支持两种格式：
        1. ```tool\n{...}\n``` （fenced code block）
        2. 行内 JSON {"tool": "...", "params": {...}}
        """
        # 先试 fenced block
        m = re.search(r"```(?:tool|json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(1))
                if "tool" in obj:
                    return obj
            except json.JSONDecodeError:
                pass

        # 再试行内 JSON
        for m in re.finditer(r"\{[^{}]*\"tool\"[^{}]*\}", text):
            try:
                obj = json.loads(m.group(0))
                if "tool" in obj:
                    return obj
            except json.JSONDecodeError:
                continue

        return None

    def _format_tool_result(self, result) -> str:
        d = result.to_dict()
        parts = [f"状态: {'成功' if d['ok'] else '失败'}"]
        if d.get("output"):
            parts.append("输出: " + str(d["output"])[:1500])
        if d.get("error"):
            parts.append("错误: " + str(d["error"])[:500])
        if d.get("duration_ms"):
            parts.append(f"耗时: {d['duration_ms']:.0f} ms")
        return "\n".join(parts)

    def _memorize_tool_call(self, tool_name: str, params: dict, result) -> None:
        """把工具调用记入智能体短期记忆。"""
        try:
            status = "成功" if result.ok else "失败"
            memo = f"调用工具 {tool_name}({params}) -> {status}"
            if result.ok and result.output is not None:
                memo += ": " + str(result.output)[:200]
            elif result.error:
                memo += ": " + str(result.error)[:200]
            # 调用基类的 _remember
            remember = getattr(self.agent, "_remember", None)
            if callable(remember):
                remember(memo)
        except Exception:
            pass


# ----------------------------------------------------------------------
# 物种中文名 + 角色定位
# ----------------------------------------------------------------------

_SPECIES_ZH: dict[str, str] = {
    "deer": "忧郁鹿",
    "squirrel": "较真松鼠",
    "butterfly": "彩纹蝶",
    "fox": "狡黠狐狸",
    "hedgehog": "戒备猔",
    "beaver": "勤恳海狸",
    "raven": "渡鸦",
    "hare": "雪兔",
    "badger": "小獾",
    "lark": "灵音雀",
    "kite": "青鸢",
}

_SPECIES_ROLE: dict[str, str] = {
    "deer": "任务编排者",
    "squirrel": "代码工程师",
    "butterfly": "UI 设计师",
    "fox": "测试工程师",
    "hedgehog": "安全工程师",
    "beaver": "运维工程师",
    "raven": "检索工程师",
    "hare": "数据分析师",
    "badger": "网络工程师",
    "lark": "监控工程师",
    "kite": "调度工程师",
}


# ----------------------------------------------------------------------
# 单例管理（按 agent_id 缓存）
# ----------------------------------------------------------------------

_FUNCTION_CALLERS: dict[str, FunctionCaller] = {}
_FUNCTION_CALLERS_LOCK = threading.Lock()


def get_function_caller(agent: Any) -> FunctionCaller:
    """获取（或创建）某个智能体专属的 FunctionCaller。"""
    try:
        agent_id = agent.get_agent_id()
    except Exception:
        agent_id = (getattr(agent, "species", "") + "-"
                    + getattr(agent, "_name_obj", ""))

    with _FUNCTION_CALLERS_LOCK:
        fc = _FUNCTION_CALLERS.get(agent_id)
        if fc is None:
            fc = FunctionCaller(agent)
            _FUNCTION_CALLERS[agent_id] = fc
        return fc


# ----------------------------------------------------------------------
# 便捷入口：给一个智能体下任务
# ----------------------------------------------------------------------

def dispatch_task_to_agent(agent: Any, task: str) -> dict:
    """把任务派给指定智能体处理。

    返回：
        {"ok": bool, "answer": str, "tool_calls": list, "rounds": int}
    """
    fc = get_function_caller(agent)
    return fc.run_task(task)


# ----------------------------------------------------------------------
# 路由：把自然语言任务派给最合适的物种
# ----------------------------------------------------------------------

def route_task_to_species(task: str) -> str:
    """根据任务文本关键词，路由到最合适的物种。

    返回物种代号（如 "squirrel"）。无匹配返回 "deer"（默认编排者）。
    """
    task_lower = task.lower()
    best_species = "deer"
    best_score = 0
    for species, keywords in SPECIES_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in task_lower:
                score += 1
        if score > best_score:
            best_score = score
            best_species = species
    return best_species


def find_agent_by_species(species: str, environment=None) -> Any:
    """从 environment 里找一个指定物种的活着的智能体。"""
    if environment is None:
        return None
    try:
        # Environment 类用 population 字段
        inhabitants = (getattr(environment, "population", None)
                       or getattr(environment, "inhabitants", None) or [])
        for a in inhabitants:
            if (getattr(a, "species", "") == species
                    and getattr(a, "_alive", False)):
                return a
    except Exception:
        pass
    return None
