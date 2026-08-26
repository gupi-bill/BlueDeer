# BlueDeer Console

> 独立前端 Agent 调度控制台 —— 纯渲染界面，所有业务/数据/权限全部交给外部多智能体调度底座（REST API）。

本项目和底座完全独立：**代码零耦合、零引用痕迹**，只通过 HTTP 调用底座公开接口。前端不内置任何业务逻辑、记忆、调度、审批运算。

## 运行

### 方式一：双击 `run.bat`（Windows）

自动起本地静态服务 `http://127.0.0.1:8081/` 并打开浏览器。

### 方式二：命令行

```bash
python -m http.server 8081
# 浏览器打开 http://127.0.0.1:8081/
```

> 前提：外部底座 REST API 运行在 `http://127.0.0.1:8000` 且已开启 CORS（跨域）。地址在 `js/api.js` 顶部 `API` 变量，可随时更换。

## 功能（7 页 · 全部对接真实接口）

| 页面 | 接口 | 说明 |
|---|---|---|
| 监控 | `/system/stats`、`/system/emergency-block/toggle` | 实时统计 + 紧急刹车开关 |
| 审批中心 | `/memories/approvals/pending`、`/memories/approvals/decide` | 待审批队列，同意/拒绝（需当前管理岗） |
| 消息调试 | `/messages/history`、`/messages/send` | 消息流 + 发送 |
| 记忆池 | `/memories/*` | 读记忆、写/删记忆（走审批） |
| 技能注册表 | `/skills/*` | 技能注册/列表/禁用 |
| 工作流 | `/workflows/*` | 画布查看、点节点编辑配置、运行、查看 run 日志 |
| Agent 列表 | `/agents/*`、`/agents/manager/*` | 节点列表、管理岗设置/撤销 |

**铁则**：每个按钮都真实调用底座 API、真实改动底座数据库，无模拟数据、无假跳转。

## 项目结构

```
BlueDeer-Console/
├── run.bat          # 双击启动器（本地静态服务 + 自动开浏览器）
├── index.html       # 入口（侧边栏导航 + 7 页）
├── main.css         # 设计系统（浅色仪表盘，CSS 变量）
└── js/              # 按页面拆分，无单文件巨型 JS
    ├── api.js       # 统一 API 请求封装（错误/离线处理）
    ├── app.js       # 路由/侧边栏/顶栏
    └── agents.js / approvals.js / messages.js / memories.js / skills.js / workflows.js / dashboard.js
```

## 说明

- 纯静态前端，无需构建，可任意静态服务器托管。
- 代码编辑器页（IDE）走 CDN `jsdelivr.net` 加载 Monaco Editor（默认离线可打开其他 6 页；IDE 页须联网）。
- 接口返回格式以底座 OpenAPI（`/docs`）为准；本仓库不包含任何底座代码。
