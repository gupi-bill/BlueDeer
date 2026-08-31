# BlueDeer 菜单 × OpenClaw 真实字段映射

> **数据源：OpenClaw 官方文档与用户本机真实配置**（docs.openclaw.ai · learnopenclaw.com · 本机 `OpenClaw/data/openclaw.json`）。
> 作用：把 BlueDeer 侧边栏每个菜单，对应到 OpenClaw 真实存在的功能与配置字段。只保留重要/必填字段，简单项省略。
> 文末附「BlueDeer Agent 系统提示词」，可直接贴进 BlueDeer 的 agent 设定。

---

## 菜单总览 → OpenClaw 概念对照

| BlueDeer 菜单 | OpenClaw 对应概念 |
|---------------|------------------|
| 概览 | Gateway 状态总览 |
| 频道 | `channels.*` |
| 实例 | Gateway 运行时 / workspace 目录 |
| 会话 | `sessions` |
| 使用情况 | `openclaw status --usage` |
| 定时任务 | `crons` / `cron` |
| 代理 | `agents.entries` + `bindings` + `identity` |
| 技能 | `skills`（SKILL.md + `skills.entries`） |
| 节点 | `flows`（ClawFlow）+ 工作流节点 |
| 配置 | `openclaw.json` 根结构 |
| 通信 | `channels` DM 策略 + Webhook/Hooks |
| 外观与设置 | `identity` |
| 自动化 | `crons` + `heartbeat` + `hooks` |
| 基础设施 | `backup` + 部署 / workspace 目录规范 |

---

## 1. 概览 (Overview)

OpenClaw Gateway 运行态快照，对应 `openclaw status --all --deep`：

| 字段 | 含义 |
|------|------|
| gateway.mode | `local`（本机） |
| gateway.port | 控制面端口，默认 `18789` |
| gateway.auth.mode | `token` / `password` |
| agents 数量 | `agents.entries` 条目数 |
| channels 数量 | `channels.*` 中 enabled 数 |
| models 主模型 | `agents.defaults.model.primary` |
| 运行健康 | `openclaw health` |

---

## 2. 频道 (Channels)

数据源：本机 `openclaw-desktop/.../extensions/` 下 27 个频道扩展的 `openclaw.plugin.json`。

**通用字段（所有频道共享）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `enabled` | boolean | 是 | 是否启用该频道 |
| `dmPolicy` | string | 是 | `pairing` \| `allowlist` \| `open` \| `disabled` |
| `allowFrom` | string[] | 条件 | `allowlist`/`open` 时允许的对方 ID |
| `accounts` | object | 多账号时 | 每账号配置（token / dmPolicy / guilds 等） |

**主流频道特有必填字段：**

| 频道 | 关键字段 |
|------|----------|
| telegram | `botToken`（或 `accounts.default.botToken`） |
| discord | `token`（bot token）/ `accounts.*.token` + `guilds.{id}.channels` |
| feishu | `appId` / `appSecret` |
| slack | `botToken` / `appToken` |
| signal | `phoneNumber` |
| whatsapp | 需 `openclaw channels login` 后再配 |
| line | `channelSecret` / `channelAccessToken` |
| msteams | `tenantId` / `appId` / `appPassword` |
| googlechat | `spaceId` / `serviceAccount` |
| matrix | `homeserver` / `accessToken` / `userId` |

> 完整 27 个平台字段见 `bluedeer-channels-config.md`。

**示例（Telegram）：**
```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "123456:ABC...",
      "dmPolicy": "pairing",
      "allowFrom": ["tg:123456789"]
    }
  }
}
```

---

## 3. 实例 (Instances)

OpenClaw 运行时目录规范（工程化部署标准）：

```
.openclaw/
├── config/            # openclaw.json、环境变量、密钥、渠道配置
├── workspace/         # 主工作区（AI 核心读写）
│   ├── data/          # 输入数据
│   ├── output/        # AI 生成结果（report/code/markdown/pdf）
│   ├── skills/        # 自定义技能
│   ├── workflows/     # 工作流定义（yml/json）
│   ├── logs/          # 运行/错误日志
│   ├── temp/          # 临时文件
│   └── assets/        # 静态资源、模板
├── models/            # 本地模型缓存
└── system/            # 系统缓存（勿手动改）
```
运行规则：输入固定在 `data/`、输出固定在 `output/`、技能在 `skills/`、工作流在 `workflows/`、日志在 `logs/`。

---

## 4. 会话 (Sessions)

| 字段 | 说明 |
|------|------|
| `session.mainKey` | 每个 agent 的「主会话」键（直接聊天落到 `agent::`） |
| `openclaw sessions cleanup` | 按磁盘预算清理过期会话 |
| context 隔离 | 每个 agentId 独立 workspace + session store |

---

## 5. 使用情况 (Usage)

OpenClaw `openclaw status --usage` 输出（provider usage / quota）：

| 字段 | 含义 |
|------|------|
| provider | 模型供应商 |
| tokens | 累计 token 用量 |
| cost | 费用（若供应商返回） |
| quota | 配额上限 |
| rateLimit | 限流状态 |

> BlueDeer「使用情况」页应展示：Token 审计、预算、限流、指标采集（对应 OpenClaw 的 usage 快照 + `agents.defaults` 上下文预算）。

---

## 6. 定时任务 (Schedule) — `crons`

**任务定义（写入 `openclaw.json` 或 `cron/jobs.json`）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | string | 是 | 任务名（出现在日志） |
| `schedule` | string | 是 | 标准 cron 表达式 `分 时 日 月 周` |
| `prompt` | string | 是 | 触发时给 agent 的指令 |
| `channel` | string | 否 | 输出发往的频道，默认主频道 |
| `agentId` | string | 否 | 指定 agent（多 agent 时） |
| `skills` | string[] | 否 | 本次任务可用的技能 |

**全局调度器配置：**
```json
{
  "cron": {
    "enabled": true,
    "maxConcurrentRuns": 2,
    "sessionRetention": "24h",
    "runLog": { "maxBytes": "2mb", "keepLines": 2000 }
  }
}
```

**示例：**
```json
{
  "crons": [
    {
      "label": "Morning Briefing",
      "schedule": "30 8 * * 1-5",
      "prompt": "汇总未读邮件、今日日历、错过的消息，给出今日 top3 重点",
      "channel": "imessage"
    }
  ]
}
```

---

## 7. 代理 (Agents)

**`agents.defaults`（默认行为）：**
```json
{
  "agents": {
    "defaults": {
      "workspace": "~/.openclaw/workspace",
      "model": {
        "primary": "anthropic/claude-sonnet-4-6",
        "fallbacks": ["openai/gpt-5.4"],
        "params": { "context1m": true }
      },
      "heartbeat": { "every": "30m", "target": "last" },
      "skills": ["github", "weather"]
    }
  }
}
```

**`agents.entries`（多 agent 定义）：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | agent 唯一标识 |
| `default` | 否 | 是否默认 agent |
| `name` | 否 | 显示名 |
| `workspace` | 否 | 独立工作区（默认规则补全） |
| `agentDir` | 否 | agent 目录 |
| `skills` | 否 | 该 agent 的技能白名单（非空即最终集合，不合并默认） |

**`bindings`（路由 inbound 到 agent）：**
```json
{
  "bindings": [
    { "agentId": "main", "match": { "channel": "telegram", "accountId": "default" } }
  ]
}
```
`binding` = 按 `(channel, accountId, peer)` + 可选 guild/team 路由到 agentId。

---

## 8. 技能 (Skills)

**SKILL.md 前置元数据（必需 + 重要可选）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 技能名 / 斜杠命令名 |
| `description` | string | 是 | 何时使用该技能 |
| `user-invocable` | boolean | 否 | 是否可作斜杠命令（默认 true） |
| `disable-model-invocation` | boolean | 否 | true 时仅显式 `$name` 调用 |
| `command-dispatch` | `"tool"` | 否 | 绕过模型直派工具 |

**`metadata.openclaw` 门控（重要项）：**

| 字段 | 说明 |
|------|------|
| `os` | 平台过滤 `darwin\|linux\|win32` |
| `requires.bins` | 必须存在的二进制 |
| `requires.env` | 必须存在的环境变量 |
| `requires.config` | 必须为真的 openclaw.json 路径 |
| `primaryEnv` | 关联 `skills.entries.<name>.apiKey` 的环境变量 |
| `install[]` | 安装器规格（brew/node/go/uv/download） |
| `skillKey` | 用此 key 取代技能名查 `skills.entries` |

**`skills.entries`（启用/配置覆盖）：**
```json
{
  "skills": {
    "entries": {
      "image-lab": {
        "enabled": true,
        "apiKey": { "source": "env", "provider": "default", "id": "GEMINI_API_KEY" },
        "env": { "GEMINI_API_KEY": "KEY" },
        "config": { "endpoint": "https://...", "model": "nano-pro" }
      }
    },
    "allowBundled": []
  }
}
```
安装：`openclaw skills install @owner/<slug>`。

---

## 9. 节点 (Nodes) — 工作流

**ClawFlow（流程层）：** `openclaw flows list|show|cancel`。它是 Background Tasks 之上的 job 级包装，拥有 flow id、owner session、waiting 状态、最小输出。

**工作流节点类型（覆盖 90% 场景）：**

| 节点 | 作用 | 关键字段 |
|------|------|----------|
| Trigger | 起点 | `type`: manual/cron/webhook/event；webhook 配 `path`/`method`/`auth` |
| LLM | 调模型推理 | `model`/`system_prompt`/`temperature`/`max_tokens`/`tools` |
| Tool | 执行操作 | `web_search`/`read_file`/`execute_command`/`http_request`/`database_query` |
| Condition | 分支 | `if`/`then`/`else`（如 `{{result.status}} == 'success'`） |
| Loop | 循环 | 批量数据处理 |
| Output | 终点 | 返回用户或发外部系统 |

**数据流：** 节点间字段映射 `{{input.text}}`，支持来自上游 / 固定值 / 上下文变量。

---

## 10. 配置 (Config) — `openclaw.json` 根结构

```json
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "bind": "loopback",
    "auth": { "mode": "token", "token": "***" },
    "controlUi": { "allowInsecureAuth": true, "dangerouslyDisableDeviceAuth": true, "allowedOrigins": ["*"] },
    "http": { "endpoints": { "chatCompletions": { "enabled": true } } }
  },
  "models": { "mode": "merge", "providers": {} },
  "agents": { "defaults": { "...": "..." }, "entries": {} },
  "channels": {},
  "commands": { "restart": true },
  "mcp": { "servers": {} },
  "skills": { "allowBundled": [] },
  "logging": { "level": "info", "redactSensitive": "tools" },
  "update": { "channel": "stable", "checkOnStart": true }
}
```
> 严格 schema 校验：未知键 / 类型错误会导致 Gateway 拒绝启动。编辑后热重载；`$schema` 是唯一允许的额外根键。

---

## 11. 通信 (Comm)

- **频道 DM 策略**：`dmPolicy` = `pairing`（需设备配对）\| `allowlist`（白名单）\| `open`（开放）\| `disabled`。
- **Webhook 触发**：工作流 Trigger 节点 `type: webhook`，配 `path`/`method`/`auth: bearer_token` 接收外部 HTTP 推送。
- **Hooks**：Gateway 级钩子，在任务前后执行。

---

## 12. 外观与设置 (Appearance) — `identity`

```json
{
  "identity": {
    "name": "Clawd",
    "emoji": "🦞",
    "theme": "helpful lobster"
  }
}
```
| 字段 | 说明 |
|------|------|
| `name` | agent 名称 |
| `emoji` | 头像 emoji |
| `theme` | 主题描述（UI 风格锚点） |

---

## 13. 自动化 (Automation)

| 机制 | 配置位置 | 作用 |
|------|----------|------|
| Cron 定时任务 | `crons` / `cron` | 周期性自动执行 |
| Heartbeat 心跳 | `agents.defaults.heartbeat` | 定期唤醒 agent 主动提醒/报告 |
| Hooks | Gateway 钩子 | 任务前后自动动作 |
| Webhooks | 工作流 Trigger | 外部事件触发 |

**heartbeat 字段：**
```json
{
  "agents": { "defaults": {
    "heartbeat": {
      "every": "30m",
      "target": "last",
      "model": "anthropic/claude-sonnet-4-6",
      "to": "+15555550123",
      "prompt": "HEARTBEAT",
      "ackMaxChars": 300
    }
  }}
}
```

---

## 14. 基础设施 (Infrastructure)

- **备份**：`openclaw backup create`（本地状态归档）/ `--only-config` / `--no-include-workspace`；`openclaw backup verify`。
- **部署**：本机（Electron 桌面）/ Docker / 云（端口 18789）。配置文件存 `/root/.openclaw/openclaw.json` 或 `~/.openclaw/openclaw.json`。
- **目录规范**：见「3. 实例」的 workspace 结构。
- **诊断**：`openclaw doctor --fix`、`openclaw health`、`openclaw status --deep`。

---

---

# 附录：BlueDeer Agent 系统提示词（可直接使用）

> 把下面这段贴进 BlueDeer「代理 / 系统提示词」配置，让 BlueDeer 各模块按 OpenClaw 真实结构定义自己。

```
你是 BlueDeer（蓝鹿）的核心 Agent，产品的每一层菜单都要对齐 OpenClaw 的真实架构与配置字段。
OpenClaw 是数据源与事实标准，以下为各模块必须遵循的真实结构：

【概览】展示 Gateway 运行态：gateway.mode/port/auth、agents 数、channels 数、主模型、健康度。
【频道】对应 OpenClaw channels.*。通用字段 enabled/dmPolicy(pairing|allowlist|open|disabled)/allowFrom/accounts；
各平台必填：telegram.botToken、discord.token、feishu.appId+appSecret、slack.botToken+appToken、
signal.phoneNumber、line.channelSecret+channelAccessToken 等。
【实例】遵循 OpenClaw workspace 工程化目录：config/ 集中配置，workspace/{data,output,skills,workflows,logs,temp,assets}/ 职责分离。
【会话】每个 agentId 独立 workspace 与 session store；main 会话 key=agent::；支持磁盘预算清理。
【使用情况】展示 provider usage/quota：tokens、cost、rateLimit；对应 OpenClaw `status --usage`。
【定时任务】结构 = crons[]：label(必填)/schedule(cron表达式,必填)/prompt(必填)/channel/agentId/skills；
全局 cron.enabled/maxConcurrentRuns/sessionRetention/runLog。
【代理】agents.defaults{workspace,model{primary,fallbacks,params},heartbeat{every,target},skills[]}；
agents.entries[]{id(必填),default,name,workspace,agentDir,skills[]}；bindings[]{agentId,match{channel,accountId,peer}}。
【技能】SKILL.md 含 name(必填)/description(必填)；metadata.openclaw 门控 os/requires.bins|env|config/primaryEnv/install/skillKey；
skills.entries{enabled,apiKey,env,config,allowBundled}。安装用 openclaw skills install @owner/<slug>。
【节点】工作流节点五类：Trigger(manual/cron/webhook/event)/LLM(model,system_prompt,temperature,max_tokens,tools)/
Tool(web_search,read_file,execute_command,http_request,database_query)/Condition(if/then/else)/Output；
数据流用 {{input.field}} 插值。ClawFlow 为任务之上的 job 包装（flows list|show|cancel）。
【配置】openclaw.json 根：gateway{port,auth,controlUi,http}/models/mcp/agents/channels/commands/skills/logging/update；
严格 schema 校验，未知键拒绝启动。
【通信】频道 DM 策略 dmPolicy；Webhook 用 Trigger 节点 type:webhook(path/method/auth:bearer_token)；支持 Gateway Hooks。
【外观】identity{name,emoji,theme}。
【自动化】cron + heartbeat{every,target,model,to,prompt,ackMaxChars} + hooks + webhooks 四件套。
【基础设施】openclaw backup create/verify；部署端口 18789；workspace 目录规范；诊断 doctor/health/status --deep。

规则：
1. 任何配置默认给出可在 openclaw.json 落地的 JSON，字段名与上面一致。
2. 仅列出重要/必填字段，简单装饰项省略。
3. 多 agent 时用 agents.entries + bindings 做隔离与路由，不混会话。
4. 工作流优先用五类节点 + {{}} 插值，不在核心层写分支逻辑（交给 authoring 层）。
5. 所有改动遵守 OpenClaw schema 严格校验，未知键会导致 Gateway 拒绝启动。
```

---

*数据来源：docs.openclaw.ai（Configuration / Multi-agent / Skills / Automation）、learnopenclaw.com（Automation / ClawFlow）、openclaw.cn（Cron）、本机 `OpenClaw/data/openclaw.json` 与 `openclaw-desktop/.../extensions/*/openclaw.plugin.json`。*
