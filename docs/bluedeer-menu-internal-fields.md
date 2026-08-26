# BlueDeer 侧边栏菜单内部功能与字段清单

> 来源：基于 `BlueDeer/templates/project_hub.html` 中 `VIEWS` 对象与 `core/` 模块映射整理。
> 图片中显示的是：概览、频道、实例、会话、使用情况、定时任务、代理/技能/节点、设置（配置/通信/外观与设置/自动化/基础设施）。

---

## 一、菜单总览

```
概览
频道
实例
会话
使用情况
定时任务

代理
  ├─ 代理
  ├─ 技能
  └─ 节点

设置
  ├─ 配置
  ├─ 通信
  ├─ 外观与设置
  ├─ 自动化
  └─ 基础设施
```

> 实际 `project_hub.html` 还包含：聊天、工作流、AI与代理、调试、日志、文档。图片里未显示，但代码里存在，文末附录补充。

---

## 二、各菜单内部详情

### 1. 概览 (overview)

**页面描述**：BlueDeer 按照 OpenClaw 基础设施层架构组织：Operator 操作器 → Claw 工作流 → Harness 可靠性执行环境。

**顶部统计卡片**（4 张）：

| 卡片名 | 值 | 含义 |
|--------|-----|------|
| Operator 操作器 | 130+ | core/ 下每个模块都是最小执行单元 |
| Claw 工作流 | 8+ | AgenticLoop / BabyAGI / CrewAI / DAG 等编排范式 |
| Harness 执行环境 | 5 | 韧性 / 可观测 / 安全 / 调度 / 生命周期 |
| 动物员工 | 11 | 多角色 Agent 隔离与协作 |

**模块分区**：

#### OpenClaw 三层核心抽象

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| Operator 操作器 | 封装 LLM 调用、函数执行、数据库查询、HTTP API 的最小执行单元 | `core/llm_utils.py` 等 |
| Claw 工作流 | 多个 Operator 按顺序/分支/循环编排成完整任务 | `core/task_orchestrator.py` |
| Harness 执行环境 | 负责重试、超时、日志、指标、追踪等非业务逻辑 | `core/healer_engine.py` |

#### 五大能力映射

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| 渠道接入 | EventBus / Webhook / MCP 统一消息入口 | `core/event_bus.py` |
| Agent 管理 | AgentRegistry / Monitor / Market 独立工作区 | `core/agent_registry.py` |
| 会话控制 | SessionStore / StateStore / Context 持久化 | `core/session_store.py` |
| 权限隔离 | Auth / SecurityGuard / Capability 边界清晰 | `core/auth.py` |
| 多角色协作 | Debate / Breakroom / CrewAI 并行协作 | `core/debate.py` |

#### 文档索引

- `docs/CORE_ARCHITECTURE.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/adr_index.md`

---

### 2. 频道 (channels)

**页面描述**：渠道接入层 —— 对应 OpenClaw 的渠道接入能力，统一消息入口与订阅路由。

**模块分区**：

#### 渠道与消息入口

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| EventBus | 通配符订阅 + 优先级的事件总线，路由规则中枢 | `core/event_bus.py` |
| Webhook | 外部渠道事件推送与 HMAC 校验 | `core/webhook.py` |
| MCP | Model Context Protocol 渠道接入 | `core/mcp.py` |
| Notifier | 通知分发器，跨渠道投递 | `core/notifier.py` |
| CommLog | 员工间通信日志 | `core/comm_log.py` |
| DeadLetterQueue | 死信队列，兜底失败消息 | `core/dead_letter_queue.py` |

#### 文档

- `docs/event_bus.md`
- `docs/notifier.md`

**若需接入外部聊天平台**，配置字段清单见 `bluedeer-channels-config.md`（已单独整理 27 个平台）。

---

### 3. 实例 (instances)

**页面描述**：运行时组件 —— 对应 OpenClaw 的 API 服务器、工作流引擎、任务队列与元数据数据库。

**模块分区**：

#### 运行时组件

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| API Server | FastAPI 服务入口 | `core/api_server.py` |
| Web Admin | Web 管理面板 | `web_admin.py` |
| CLI TUI | 命令行交互界面 | `core/cli_tui.py` |
| TUI Renderer | 终端渲染器 | `core/tui_renderer.py` |
| Database | SQLite 元数据数据库 | `core/database.py` |
| GracefulShutdown | 优雅停机与生命周期 | `core/graceful_shutdown.py` |

#### 文档

- `docs/launchers_usage.md`

---

### 4. 会话 (sessions)

**页面描述**：会话控制层 —— 对应 OpenClaw 的会话控制与状态管理，支持断点续跑。

**模块分区**：

#### 会话与状态持久化

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| SessionStore | 会话存储与隔离 | `core/session_store.py` |
| StateStore | 执行状态持久化，断点续跑 | `core/state_store.py` |
| Context | 三层上下文管理 | `core/context.py` |
| Database | SQLite 本地存储 | `core/database.py` |
| Backup | 状态备份与恢复 | `core/backup.py` |
| Cleanup | 过期会话清理 | `core/cleanup.py` |

**核心数据表**（`BlueDeer/data/bluedeer.db`）：

- `session` 表：id、title、model、directory、time_updated、time_archived 等。
- 状态字段参考：RUNNING / IDLE / STOPPED。

---

### 5. 使用情况 (usage)

**页面描述**：资源治理 —— 对应 OpenClaw Harness 的指标采集与资源限流。

**模块分区**：

#### Token 与资源治理

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| TokenAuditor | Token 审计器 | `core/token_auditor.py` |
| TokenBudget | Token 预算器 | `core/token_budget.py` |
| TokenBucket | 令牌桶限流 | `core/token_bucket.py` |
| CompositeLimiter | 组合限流器 | `core/composite_limiter.py` |
| MetricsCollector | 关键指标采集 | `core/metrics_collector.py` |
| Observability | 可观测性抽象 | `core/observability.py` |

**关键监控指标字段**（供前端展示用）：

```json
{
  "tokens_input": 0,
  "tokens_output": 0,
  "tokens_total": 0,
  "cost_usd": 0.0,
  "request_count": 0,
  "error_count": 0,
  "latency_ms_avg": 0,
  "throttled_count": 0
}
```

---

### 6. 定时任务 (schedule)

**页面描述**：调度编排 —— 对应 OpenClaw 的 Claw 工作流调度与 DAG 执行计划。

**模块分区**：

#### 调度核心

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| Scheduler | 定时任务调度器 | `core/scheduler.py` |
| TaskDAG | 任务依赖 DAG 与执行计划 | `core/task_dag.py` |
| DAGTemplates | DAG 模板集合 | `core/dag_templates.py` |
| Gantt | 甘特图与时序安排 | `core/gantt.py` |
| TaskTemplates | 任务模板引擎 | `core/task_templates.py` |
| TimeoutCtrl | 任务超时控制 | `core/timeout_ctrl.py` |

#### 文档

- `docs/scheduler.md`
- `docs/task_orchestrator.md`

**任务配置字段示例**：

```json
{
  "task_id": "task_001",
  "name": "每日巡检",
  "schedule": "0 9 * * *",
  "timezone": "Asia/Shanghai",
  "dag": ["step1", "step2"],
  "agent": "忧郁鹿",
  "enabled": true,
  "timeout_seconds": 300,
  "retry_count": 3
}
```

---

## 三、代理分组

### 7. 代理 (agents)

**页面描述**：Agent 管理层 —— 对应 OpenClaw 的 Agent 隔离与多角色协作。

**员工展示**（11 位动物员工卡片）：

| 名字 | 角色 | 头像颜色 | emoji |
|------|------|----------|-------|
| 忧郁鹿 | 调度官 | #A3826E | 🦌 |
| 机灵鼠 | 前端工程师 | #9C7B5E | 🐭 |
| 绘羽蝶 | 视觉设计师 | #A07AA5 | 🦋 |
| 赤谋狐 | 测试工程师 | #B86E4E | 🦊 |
| 针客猬 | 安全工程师 | #7A5D44 | 🦔 |
| 大坝狸 | 基建工程师 | #85603F | 🦫 |
| 黑卷鸦 | 记忆管理员 | #4A5560 | 🐦‍⬛ |
| 霜耳兔 | 快递员 | #C8BFB0 | 🐇 |
| 土工獾 | 矿工 | #5A5550 | 🦡 |
| 清音雀 | 播音员 | #C9925A | 🐦 |
| 天瞰鸢 | 瞭望员 | #6B7A95 | 🪁 |

**模块分区**：

#### Agent 基础设施

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| BaseAgent | Agent 基类与生命周期 | `core/base_agent.py` |
| AgentRegistry | Agent 注册表，独立工作区 | `core/agent_registry.py` |
| AgentMonitor | Agent 运行监控 | `core/agent_monitor.py` |
| AgentMarket | Agent 市场与发现 | `core/agent_market.py` |
| AgentIntegration | Agent 外部集成 | `core/agent_integration.py` |
| Capability | 能力模型与权限边界 | `core/capability.py` |
| AchievementSystem | 成就系统 | `core/achievement_system.py` |
| RewardSettler | 奖励结算 | `core/reward_settler.py` |

#### 文档

- `BlueDeer/员工设定规范.md`

**Agent 定义字段示例**：

```json
{
  "id": "agent_001",
  "name": "忧郁鹿",
  "role": "调度官",
  "color": "#A3826E",
  "emoji": "🦌",
  "capabilities": ["dispatch", "plan"],
  "model": "qwen2.5vl:7b",
  "workspace": "./workspace/忧郁鹿"
}
```

---

### 8. 技能 (skills)

**页面描述**：Operator 技能体系 —— 对应 OpenClaw 的 Operator 操作器与编排范式。

**模块分区**：

#### 编排范式（Claw 实现）

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| AgenticLoop | 通用 Agentic 循环 | `core/agentic_loop.py` |
| BabyAGILoop | BabyAGI 任务队列式循环 | `core/babyagi_loop.py` |
| CrewAIStyle | CrewAI 角色协作风格 | `core/crewai_style.py` |
| LangGraphStyle | LangGraph 状态图风格 | `core/langgraph_style.py` |
| OpenDevinStyle | OpenDevin 软件工程风格 | `core/opendevin_style.py` |
| AgentGPTStyle | AgentGPT 自主目标风格 | `core/agentgpt_style.py` |
| Debate | 多 Agent 辩论 | `core/debate.py` |
| Capability | 能力等级与权限 | `core/capability.py` |

#### 文档

- `BlueDeer/智能体进化/BlueDeer智能体进化增强实施提示词_2026-08-17.md`

---

### 9. 节点 (nodes)

**页面描述**：工作流节点编排 —— 对应 OpenClaw 的 Claw 工作流节点与数据流。

**模块分区**：

#### 工作流节点

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| TaskOrchestrator | 多 Agent 任务编排器 | `core/task_orchestrator.py` |
| TaskBoard | 任务看板与状态 | `core/task_board.py` |
| TaskDispatcher | 任务分发到具体 Agent | `core/task_dispatcher.py` |
| TaskDAG | DAG 节点依赖 | `core/task_dag.py` |
| Stream | 流式处理管线 | `core/stream.py` |
| Graph | 图结构数据流 | `core/graph.py` |

---

## 四、设置分组

### 10. 配置 (config)

**页面描述**：配置治理 —— 对应 OpenClaw 的权限隔离与护栏策略。

**模块分区**：

#### 配置与治理

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| Config | 配置管理与热重载 | `core/config.py` |
| GuardrailConfig | 护栏配置 | `core/guardrail_config.py` |
| PolicyEngine | 策略引擎 | `core/policy_engine.py` |
| InputValidator | 输入校验 | `core/input_validator.py` |
| HitlManager | 人在回路管理 | `core/hitl_manager.py` |
| Auth | 认证与授权 | `core/auth.py` |

#### 文档

- `BlueDeer/操作规范.md`

**核心配置字段示例**：

```json
{
  "gateway": {
    "port": 18789,
    "token": "",
    "dangerouslyDisableDeviceAuth": false
  },
  "mcp": {
    "servers": {}
  },
  "channels": {},
  "models": {
    "default": "qwen2.5vl:7b"
  },
  "auth": {
    "enabled": true,
    "mode": "token"
  },
  "guardrails": {
    "max_tokens_per_request": 8192,
    "allow_shell": false,
    "hitl_required": false
  }
}
```

---

### 11. 通信 (comm)

**页面描述**：通信协议 —— 对应 OpenClaw 的 Agent 间标准通信与事件协议。

**模块分区**：

#### 通信协议

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| EventBus | 通配符订阅事件协议 | `core/event_bus.py` |
| Webhook | 外部事件推送协议 | `core/webhook.py` |
| Notifier | 通知分发协议 | `core/notifier.py` |
| MCP | Model Context Protocol | `core/mcp.py` |
| CommLog | 通信记录与审计 | `core/comm_log.py` |

#### 文档

- `docs/event_bus.md`
- `docs/notifier.md`

**EventBus 消息格式示例**：

```json
{
  "topic": "agent.忧郁鹿.task.complete",
  "payload": {
    "task_id": "task_001",
    "status": "success",
    "result": "..."
  },
  "timestamp": 1692230400000,
  "priority": 1
}
```

---

### 12. 外观与设置 (appearance)

**页面描述**：主题与视觉资产 —— 对应 OpenClaw 的 Web 控制台与终端界面。

**模块分区**：

#### 视觉与主题

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| Avatars | 员工头像资产 | `modules/avatars.py` |
| SceneAssets | 场景资产 | `modules/scene_assets.py` |
| PixelCanvas | 像素画布 | `core/pixel_canvas.py` |
| Canvas | 画布渲染 | `core/canvas.py` |
| Scene | 场景管理 | `core/scene.py` |
| TUI Renderer | 终端界面渲染 | `core/tui_renderer.py` |

#### 文档

- `BlueDeer/工作流编辑器风格规范.md`

**CSS 主题变量**（来自 `project_hub.html` `:root`）：

```css
:root {
  --bg: #f5f7fb;
  --sidebar-bg: rgba(255,255,255,0.86);
  --panel: #ffffff;
  --border: #e6ebf2;
  --text: #1f2937;
  --accent: #3b82f6;
  --accent-2: #6366f1;
  --green: #10b981;
  --amber: #f59e0b;
  --red: #ef4444;
  --radius: 16px;
}
```

---

### 13. 自动化 (automation)

**页面描述**：Harness 自动化层 —— 对应 OpenClaw Harness 的韧性设计与自愈能力。

**模块分区**：

#### Harness 韧性自动化

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| HealerEngine | 自愈引擎 | `core/healer_engine.py` |
| CircuitBreaker | 熔断器 | `core/circuit_breaker.py` |
| Retry | 重试策略 | `core/retry.py` |
| RetryHandler | 重试处理器 | `core/retry_handler.py` |
| DeadLetterQueue | 死信队列 | `core/dead_letter_queue.py` |
| TaskOrchestrator | 多 Agent 任务编排 | `core/task_orchestrator.py` |
| Scheduler | 定时自动化 | `core/scheduler.py` |
| DreamEngine | 梦引擎自动化 | `core/dream_engine.py` |

#### 文档

- `BlueDeer/智能体进化/BlueDeer可视化工作流模块实施提示词_2026-08-17.md`

**自愈策略字段示例**：

```json
{
  "healer": {
    "enabled": true,
    "max_retries": 3,
    "backoff": "exponential",
    "circuit_breaker_threshold": 5,
    "dead_letter_enabled": true
  }
}
```

---

### 14. 基础设施 (infra)

**页面描述**：部署与依赖 —— 对应 OpenClaw 的本地 / Docker / 云原生部署运行时。

**模块分区**：

#### 运行依赖

| 模块 | 功能 | 源码文件 / 外部依赖 |
|------|------|---------------------|
| Ollama | 本地 LLM 推理（默认 qwen2.5vl:7b） | external |
| Obsidian Bill | 长期记忆知识库 | external |
| OpenCode | Agent 桌面主界面 | external |
| OpenClaw | 视觉 Agent / 桌面控制 | external |
| Database | SQLite 元数据数据库 | `core/database.py` |
| SessionStore | 会话存储 | `core/session_store.py` |
| StateStore | 状态存储 | `core/state_store.py` |
| GitOps | Git 操作 | `core/git_ops.py` |

---

## 五、附录：图片中未显示但实际存在的菜单

### 聊天 (chat)

**内部功能**：
- 聊天头部标题
- 员工选择条（employee-bar）：11 位动物员工 pill
- 消息区域（messages）：用户/AI 气泡对话
- 工具栏：新对话、文件、图片、下载、语音输入
- 输入框：文本输入 + 发送按钮
- 语音识别：基于 `webkitSpeechRecognition`，语言 `zh-CN`

**核心交互字段**：

```json
{
  "message": {
    "role": "user|ai",
    "name": "忧郁鹿",
    "content": "...",
    "timestamp": 1692230400000
  }
}
```

### 工作流 (workflow)

**内部功能**：
- 内嵌 iframe，加载 `workflow.html`
- 可视化工作流编辑器

### AI与代理 (aiagents)

**模块分区**：

#### AI 核心（Operator 层）

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| LLMUtils | LLM 工具集与模型路由 | `core/llm_utils.py` |
| RAG | 检索增强生成管线 | `core/rag.py` |
| MemoryConsolidator | 长期记忆固化 | `core/memory_consolidator.py` |
| MemoryExtractor | 记忆提取 | `core/memory_extractor.py` |
| VectorBrowser | 向量数据库浏览 | `core/vector_browser.py` |
| GitHubKnowledge | GitHub 知识库集成 | `core/github_knowledge.py` |
| DreamEngine | 梦引擎 | `core/dream_engine.py` |

### 调试 (debug)

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| Debugger | 调试器 | `core/debugger.py` |
| Tracer | 执行轨迹追踪 | `core/tracer.py` |
| Observability | 可观测性抽象 | `core/observability.py` |
| MetricsCollector | 指标采集 | `core/metrics_collector.py` |
| TestRunner | 测试运行器 | `core/test_runner.py` |
| SecurityScanner | 安全扫描器 | `core/security_scanner.py` |

### 日志 (logs)

| 模块 | 功能 | 源码文件 |
|------|------|----------|
| LogViewer | 日志查看器 | `core/log_viewer.py` |
| Logger | 结构化日志记录器 | `core/logger.py` |
| Audit | 审计日志 | `core/audit.py` |
| SecurityReport | 安全报告 | `core/security_report.py` |
| Reporter | 报告生成器 | `core/reporter.py` |
| DreamReport | 梦报告 | `core/dream_report.py` |

### 文档 (docs)

**内部功能**：项目文档索引（docs/），列出 20 个文档链接。

---

## 六、通用前端组件字段

### info-card（概览统计卡片）

```json
{
  "label": "Operator 操作器",
  "value": "130+",
  "note": "core/ 下每个模块都是最小执行单元"
}
```

### module-card（模块卡片）

```json
{
  "name": "EventBus",
  "desc": "通配符订阅 + 优先级的事件总线",
  "file": "core/event_bus.py"
}
```

### doc-card（文档卡片）

```json
{
  "name": "核心架构",
  "file": "docs/CORE_ARCHITECTURE.md",
  "path": "file:///C:/Users/a/Desktop/vibe%20coding/BlueDeer/docs/CORE_ARCHITECTURE.md"
}
```

### emp-card（员工卡片）

```json
{
  "color": "#A3826E",
  "name": "忧郁鹿",
  "role": "调度官",
  "emoji": "🦌"
}
```
