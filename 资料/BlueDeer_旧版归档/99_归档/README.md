# 🦌 BlueDeer 控制台

> 忧郁鹿森林公司 · 多智能体协同办公系统 —— 一个把 **OpenClaw 网关**、**本地推理（Ollama）**、**云端 API** 和 **多智能体工作流** 拧进一个浏览器控制台的全栈项目。

![python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![fastapi](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![openclaw](https://img.shields.io/badge/OpenClaw-2026.6.11-8B5CF6)
![license](https://img.shields.io/badge/License-MIT-10b981)

---

## ✨ 这是什么

BlueDeer 是一个**自托管的 AI 工作台控制台**：

- 🎛️ **控制台**：OpenClaw 风格仪表盘 —— 概览 / 频道 / 实例 / 会话 / 使用情况 / 定时任务 / 代理 / 技能 / 节点 / 配置 / 通信 / 外观 / 自动化 / 基础设施 / 调试 / 日志 / 文档，17 个菜单全部**真实数据、真实可操作**。
- 🧠 **真联动**：不是静态壳 —— 通过 OpenClaw 网关官方通道拉取**真实 agent（如「凯哥（王子凯）」）、真实会话、真实技能、真实定时任务**；MCP 服务器可**接入 / 启停 / 删除**，写配置自动备份并热重载。
- 🗂️ **办公室平面图**：2.5D 森林公司平面图，员工点击定位。
- 🖥️ **OpenClaw 控制台内嵌**：一键 iframe 内嵌 OpenClaw 原生控制台，实时聊天、管理频道/会话/定时任务/技能。

## 🚀 快速开始

### 方式一：双击运行（Windows）

```bash
# 双击即可
run_local.py
```

会自动：拉起 OpenClaw 网关（若未运行）→ 启动本地 Web 服务 → 打开浏览器。

### 方式二：命令行

```bash
# 安装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 启动
.venv\Scripts\python run_local.py
# 或
.venv\Scripts\python -m uvicorn web_server:app --host 127.0.0.1 --port 8080
```

打开 **http://127.0.0.1:8080/** 即可。

### 依赖的外部服务（可选，缺了控制台会如实显示「离线」）

| 服务 | 用途 | 默认地址 |
|---|---|---|
| [OpenClaw](https://docs.openclaw.ai) 网关 | Agent 运行时 / 真实数据源 | `ws://127.0.0.1:18789` |
| [Ollama](https://ollama.com) | 本地推理（默认模型 `qwen2.5vl-tools:7b`） | `http://127.0.0.1:11434` |
| 云端 API（可选） | SiliconFlow / DeepSeek / GitHub Models / 智谱 | 控制台内配置 |

> 没有这些服务，控制台依然能跑（Web 本身在 127.0.0.1），只是对应模块显示离线——**如实展示，绝不造假**。

## 🎯 控制台功能一览

| 菜单 | 内容 | 可操作 |
|---|---|---|
| 概览 | 网关/模型/会话健康分、实时徽章 | 刷新 |
| 代理 | 真实 OpenClaw agent（身份/模型） | ✅ 编辑身份（名字/emoji） |
| 配置 | openclaw.json 编辑器 + MCP 管理 | ✅ 接入/启停/删除 MCP、保存配置 |
| 定时任务 | 真实 cron 列表 | ✅ 新建 / 启停 / 删除 |
| 会话 | OpenClaw 真实会话列表 | 跳转控制台 |
| 频道 | 真实频道配置 | 跳转控制台登录 |
| 技能 | 磁盘直读技能清单（内置 + ClawHub） | 刷新 |
| 日志 | 网关日志（磁盘直读，秒开） | 刷新 |
| 调试 | health / 模型 / 任务快照 | 刷新 |
| OpenClaw 控制台 | iframe 内嵌官方控制台 | ✅ 全功能 |

**外观**：浅色/深色 × 玻璃拟态/扁平极简/赛博霓虹/夜森林 4 种质感 × 5 种主题色，任意叠加。

## 🗂️ 项目结构

```
BlueDeer/
├── run_local.py          # 双击启动器（自动拉起 OpenClaw 网关 + 开浏览器）
├── web_server/           # FastAPI 后端
│   ├── app.py            # 主应用：dashboard 数据源 + OpenClaw 可操作 API
│   └── routes_pages.py   # 页面路由（控制台 / 平面图）
├── templates/
│   ├── project_hub.html  # BlueDeer 控制台（单页，17 视图）
│   └── index.html        # 夜森林外壳
├── core/                 # 多智能体引擎（DAG/编排/分发/看板/流式…）
├── docs/                 # 架构与设计文档
└── data/                 # 运行时数据（不入库）
```

## 🔌 OpenClaw 真实联动原理

OpenClaw 控制 UI 走 **WebSocket RPC**（`connect` → `connect.challenge` → 设备身份 Ed25519 签名）。BlueDeer 不重复造轮子，直接以 **OpenClaw 官方 CLI 作为网关客户端**拉取真实数据（`status / agents list / channels list / cron / models`），列表类改**磁盘直读**保证毫秒级响应，写操作（增删改）低频调用 CLI 真实生效。

## ⚠️ 说明

- 本仓库为作者本机配置（含绝对路径），clone 后请按需修改 `web_server/app.py` / `run_local.py` 顶部的路径常量。
- `data/`、`.venv/`、密钥、备份目录均不提交。
- 仅绑定 `127.0.0.1`，不暴露公网。

## 📄 License

MIT
