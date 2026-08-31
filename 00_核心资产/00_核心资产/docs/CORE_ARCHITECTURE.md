# BlueDeer Core Code Architecture

## 1. 总体分层

```
BlueDeer/
├── core/                    # 核心运行时
│   ├── base_agent.py        # Agent 基类（生命周期 / 消息 / 风格）
│   ├── task.py              # 任务模型：Task / TaskResult / Message / TokenUsage
│   ├── event_bus.py         # 异步事件总线（通配符订阅 / 优先级）
│   ├── task_orchestrator.py # DAG 编排器（并行 / 超时 / 重试 / 回滚）
│   ├── harness.py           # 全局调度器（任务下发 / 结果汇总 / 熔断）
│   ├── config.py            # 统一配置（热重载 / env 覆盖）
│   ├── context.py           # 三层上下文（global / agent / task）
│   ├── agentic_loop.py      # 007-AutoGPT：canonical agentic loop
│   ├── babyagi_loop.py      # 007-BabyAGI：3-agent loop + 向量记忆
│   ├── crewai_style.py      # 007-CrewAI：role / task / crew / flow
│   ├── langgraph_style.py   # 007-LangGraph：StateGraph + checkpoint
│   ├── agentgpt_style.py    # 007-AgentGPT：goal-driven browser agent
│   └── opendevin_style.py   # 007-OpenDevin：dev plan/write/execute/debug
├── models/                  # LLM 路由与适配
├── tools/                   # 工具注册与执行
├── modules/                 # 业务模块（sparrow / scene_assets 等）
└── digital_life/            # 数字生命子域（animal agents / memory / channels）
```

### 1.1 前端模块（game_frontend）

`game_frontend.py` 是前端入口：`render_homepage()` 渲染首页、`get_frontend_status()` 聚合前端状态。浏览器看到的全部画面（80×60 大地图、17 功能区、11 只像素动物、顶部菜单）以静态 HTML/CSS/JS 存在 `templates/index.html`（12994 行），由 Python 用 `Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")` 读取注入，浏览器不依赖任何外部下载。原单文件内嵌 13165 行，已拆为模板文件 + 文件读取（详见 `docs/NEXT_SPRINT.md` 009 系列）。

## 2. 核心数据流

1. **任务创建**：Harness.submit_task 生成 Task，写入 pending + 下发到 agent topic
2. **任务执行**：BaseAgent.handle 接收 Task → 构建 prompt → Router 推理 → ToolRegistry 执行 → 自检
3. **结果回传**：TaskResult 发布到 RESULT_TOPIC → Harness._on_result 汇总
4. **故障处理**：超时熔断 / 指数退避重试 / 负载均衡重分配

## 3. 007-Agent 架构矩阵

| Agent | 核心模式 | 状态管理 | 协调原语 |
|-------|---------|---------|---------|
| AutoGPT | agentic loop | AgenticLoopState | 单 Agent 循环 |
| BabyAGI | 3-agent loop | BabyAGIState | task queue |
| CrewAI | role-based crew | CrewDef | TaskDef 传递 |
| LangGraph | state graph | StateGraph | node / edge / checkpoint |
| AgentGPT | goal-driven | AgentGPTResult | 任务序列 |
| OpenDevin | dev loop | list[DevTask] | 步骤序列 |

## 4. 007-Agent 集成模式

### 4.1 AutoGPT / AgentGPT / BabyAGI
- 继承 `BaseAgent`，复用 `handle()` 的 prompt → model → tool → self-check 闭环
- 自主循环由 `run()` / `run_autonomous()` / `run_goal()` 驱动，不依赖 Harness
- 可接入 Harness：将 `LoopState` 序列化为 Task，下发到 EventBus

### 4.2 CrewAI
- `CrewAIFlow` 为纯编排层，不继承 BaseAgent
- 建议后续接入：每个 `AgentDef` 对应一个 BaseAgent 实例
- `CrewDef` 序列化为 Task DAG，由 TaskOrchestrator 并行执行

### 4.3 LangGraph
- `StateGraph` 为纯状态机，不依赖 BaseAgent
- 每个 Node 可封装为 BaseAgent.handle
- `checkpoint()` 输出对接 TaskOrchestrator.save_state / load_state

### 4.4 OpenDevin
- `DeveloperAgent` 继承 BaseAgent，复用 tool execution
- 代码执行建议接入 `core/task_orchestrator.py` 的 `run_concurrent`

## 5. 自迭代优化路线

| 阶段 | 优化项 | 预期收益 |
|------|--------|----------|
| P1 | 007 Agent 统一接入 Harness / EventBus | 复用现有任务生命周期 |
| P2 | LangGraph checkpoint 对接 TaskOrchestrator | 持久化 + 恢复 |
| P3 | BabyAGI 向量记忆替换为 ContextManager + vector_db | 统一记忆层 |
| P4 | CrewAI Flow 封装为 EventBus 状态机 | 事件驱动编排 |
| P5 | 大文件拆分（security.py / harness.py / reward.py） | 可维护性 |
| P6 | TaskOrchestrator asyncio 化 | 并发性能提升 |
| P7 | game_frontend.py 拆分（13165→172 行，HTML 抽 templates/index.html） | 已完成示例，证明拆分路线可行 |
