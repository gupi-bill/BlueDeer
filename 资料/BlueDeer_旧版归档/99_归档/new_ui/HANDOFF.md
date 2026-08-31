# new_ui 交接文档（Handoff）

> 交给专业写代码的同学。以下是从「办公主管」视角整理的全部现状、改动、规则与待办。

## 一、需求方规则（最高优先级，8 条）

1. 保留整个仓库，**不归档、不删旧代码**。新页面全部写在 `new_ui/`，老代码原地当素材库，不改动。
2. 老的巨型 html、废弃前端文件**不动、只注释，不再作为主入口**。
3. `new_ui/` 只做一件事：调用 `Agent-Rotary-Station` 的远程 HTTP API，**内部不写任何业务逻辑、审批、记忆运算**。
4. new_ui 优先只做 3 个页面（已完成）：Agent 列表 / 审批中心 / 消息调试面板。
5. 样式去塑料感：从旧代码复制配色/头像/角色素材；删霓虹发光、粒子动画、多层阴影；统一间距字号。
6. **硬性规则：每做一个页面，必须同步对接对应底座 API，按钮必须真实生效，禁止假模块、假跳转。**
7. 开发顺序：3 页面调通 → git 提交（已完成）→ 之后逐个新增记忆、工作流画布等页面。
8. 本地调试：ARS 后端务必开 CORS（已开，见下）。

## 二、当前完成状态（已完成 ✅）

| 页面 | 功能 | 真实生效验证 |
|---|---|---|
| Agent 列表 | 拉 `/agents` 显示节点 + 管理岗设置/撤销 | ✅ 实测设→查→撤全链路真 |
| 审批中心 | 读待审批队列 + 同意/拒绝 | ✅ 实测同意→approved→记忆真落库 |
| 消息调试 | 消息流展示 + 发送 | ✅ 实测发送→history 可见 |

样式：干净浅色（底 #f4f5f7 + 白卡片 + 细边框），无霓虹/无粒子/无多层阴影，统一 16px 间距、13-14px 字号，agent 首字母圆形头像。

## 三、文件与改动清单

**BlueDeer 仓库**（`<WORKSPACE_DIR>\BlueDeer`）
- `new_ui/index.html` — 新调度台（唯一新增文件，23KB，单页 3 tab）
- `web_server/app.py` — 只加 3 行静态挂载：
  ```python
  if os.path.isdir("new_ui"):
      app.mount("/new_ui", StaticFiles(directory="new_ui", html=True), name="new_ui")
  ```
- git 提交：`55a52fa feat(new_ui): Agent-Rotary-Station 调度台 — 3 页面全真实 API`

**ARS 仓库**（`<WORKSPACE_DIR>\Agent-Rotary-Station`）
- `app/main.py` — 加 CORS 中间件（`allow_origins=["*"]`，全方法全头）
- git 提交：`62d505e feat: 开启 CORS 跨域`

## 四、服务与访问

- BlueDeer Web：`http://127.0.0.1:8080/`（老控制台） / `http://127.0.0.1:8080/new_ui/`（新调度台）
- ARS 底座：`http://127.0.0.1:8000/`（FastAPI，docs 在 /docs）
- 启动：BlueDeer 用 `run_local.py`；ARS 用 `run.bat`（uvicorn 127.0.0.1:8000）

## 五、ARS API 参考（3 页已用到）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/agents` | GET | Agent 列表：`{ok, agents:[{agent_id,name,role,status,capabilities,last_seen}]}`，role ∈ worker/manager/toolnode |
| `/agents/manager/set` | POST | `{agent_id}` 设管理岗 |
| `/agents/manager/current` | GET | 当前管理岗 `{ok, manager}` |
| `/agents/manager/clear` | POST | 撤销管理岗 |
| `/memories/approvals/pending` | GET | 待审批队列 `{ok, pending:[{request_id,agent_id,domain,action,payload,status,...}]}` |
| `/memories/approvals/decide` | POST | `{request_id, manager_id, approve:bool}` —— **仅当前管理岗可审批**（403） |
| `/messages/send` | POST | `{channel_type: private|group|task, from_agent, to_agent, task_id, content}` |
| `/messages/history` | GET | `?limit=50` 消息流水，按时间正序 |
| `/memories/write` | POST | 写记忆会先建审批单（pending）→ 需管理岗 decide |
| `/memories/read` | GET | `?reader=&domain=&mem_key=` 读记忆（可验证审批结果落库） |

> 完整 schema 见 `app/schemas.py`；审计日志 `/system/audit-logs`。

## 六、待办（用户规则第 7 条的后续）

1. **记忆页面** — 对应 `/memories/*`：读/写/删除（写删需走审批，页面要体现"提交后待审批"）。
2. **工作流画布页面** — 对应 `/workflows/*`（路由在 `app/routers/workflows.py`，尚未细读，需先摸接口）。
3. 其余底座能力可选做：技能市场（`/skills/*`）、工具队列（`/tools/*`）、任务（`/tasks/*`）、紧急刹车（`/system/emergency-block/*`）。

## 七、注意点

- **审批必须管理岗**：decide 接口 403 除非 `manager_id` == 当前管理岗。页面前端要显示"当前无管理岗"的引导（已做）。
- **CORS 已开**但 `allow_origins=["*"]` 是开发配置，上公网前应收紧。
- **测试痕迹**：ARS 里留了联调数据（agent：x/mgr1/worker1；消息若干；一条已审批记忆 `note:test`），是真实数据，不影响开发，介意可清。
- **写操作**（管理岗/审批/发消息）在页面里都即时刷新列表，无假按钮。
- 老控制台（project_hub.html 17 视图）已另有 OpenClaw 联动功能，与新 new_ui 互不干扰，**不要合并**。
