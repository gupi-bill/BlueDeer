# 🦌 BlueDeer 项目（初版）

> 忧郁鹿森林公司 · 多智能体协同办公系统

---

## 📦 项目结构

```
BlueDeer_初版/
├── BlueDeer/              ← 全部合一：主控制台 + Agent底座 + 前端调度台
│   ├── run_local.py       一键启动器（一条命令全起）
│   ├── web_server/        FastAPI 后端
│   │   ├── app.py         主应用
│   │   ├── routes_*.py    路由模块（含新增 routes_agent.py）
│   │   └── ...
│   ├── templates/         HTML 模板（控制台17视图 + 平面图）
│   ├── static/            静态资源（角色图、精灵图）
│   ├── core/              多智能体引擎（DAG/编排/分发/看板/流式…）
│   ├── modules/           11 只动物员工模块
│   ├── agent/             Agent 底座（13层骨架 + REST API）
│   ├── console/           Agent 调度台前端（7页，纯静态）
│   ├── new_ui/            Agent-Rotary-Station 调度台重制版
│   ├── models/            模型路由（Ollama/SiliconFlow/DeepSeek/智谱）
│   ├── tools/             工具注册表 + 内置工具
│   ├── vector_db/         向量数据库
│   ├── memory_archive/    动物记忆存档
│   ├── cli/               命令行工具
│   ├── docs/              架构与设计文档
│   ├── tests/             单元测试
│   ├── scripts/           工程脚本（预提交/安全扫描/基准测试）
│   ├── reports/           审计报告
│   ├── 00_核心资产/       精选资产
│   └── .github/           GitHub Actions CI
└── 资料/                  归档资料（旧版、历史报告）
```

---

## 🚀 一键启动

```bash
cd BlueDeer_初版/BlueDeer
python run_local.py
```

**启动后自动打开浏览器 → http://127.0.0.1:8080/**

同时提供：
- **主控制台**：http://127.0.0.1:8080/ （OpenClaw 风格仪表盘，17视图）
- **Agent 调度台**：http://127.0.0.1:8080/console/ （7页全功能调度台）
- **Agent API**：http://127.0.0.1:8080/agent/ （REST API，供调度台调用）

---

## 🎯 功能一览

### 主控制台（/）
| 菜单 | 内容 | 可操作 |
|---|---|---|
| 概览 | 网关/模型/会话健康分 | 刷新 |
| 代理 | OpenClaw 真实 agent | ✅ 编辑身份 |
| 配置 | openclaw.json 编辑器 + MCP | ✅ 接入/启停/删除 |
| 定时任务 | 真实 cron 列表 | ✅ 新建/启停/删除 |
| 会话/频道 | 真实数据 | 跳转控制台 |
| OpenClaw 控制台 | iframe 内嵌 | ✅ 全功能 |

### Agent 调度台（/console/）
| 页面 | 功能 |
|---|---|
| 总览 | 实时统计 + 紧急刹车 |
| 审批中心 | 待审批队列 + 同意/拒绝 |
| 聊天会话 | 消息流 + 发送 |
| 记忆池 | 读/写/删记忆（走审批） |
| 技能注册表 | 技能注册/列表/禁用 |
| 工作流 | 画布查看 + 运行 |
| Agent 列表 | 节点管理 + 管理岗设置 |

---

## 🔌 依赖的外部服务（可选）

| 服务 | 用途 | 默认地址 |
|---|---|---|
| [OpenClaw](https://docs.openclaw.ai) 网关 | Agent 运行时 / 真实数据源 | `ws://127.0.0.1:18789` |
| [Ollama](https://ollama.com) | 本地推理 | `http://127.0.0.1:11434` |

> 没有这些服务，控制台依然能跑，对应模块显示「离线」。

---

## ⚠️ 说明

- 本仓库为作者本机配置（含绝对路径），clone 后请按需修改 `web_server/app.py` / `run_local.py` 顶部的路径常量。
- `data/`、`.venv/`、密钥、备份目录均不提交。
- 仅绑定 `127.0.0.1`，不暴露公网。

---

## 📄 License

MIT
