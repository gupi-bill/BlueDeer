# Game Router 路由规则配置文档

## 1. 路由架构

Game Router 将游戏功能集成到 FastAPI，作为 APIRouter 挂载到 `/game/` 前缀。

```
/game/           → 主游戏页面（2D 俯视角）
/game/map        → 2.5D 地图页面
/game/console    → 极简控制台页面
/game/report     → 进化报告页面
/game/story      → 故事章节页面
/game/snap       → 生态快照页面
```

## 2. API 端点

### 2.1 状态查询

| 端点 | 方法 | 说明 |
|------|------|------|
| `/game/api/status` | GET | 实时生物圈状态 |
| `/game/api/story` | GET | 故事章节（支持 since 时间戳过滤） |
| `/game/api/report` | GET | 进化报告 |
| `/game/api/snap` | GET | 生态快照 |

### 2.2 任务管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/game/api/inject` | POST | 注入任务 |
| `/game/api/tasks` | GET | 任务列表 |

### 2.3 交互控制

| 端点 | 方法 | 说明 |
|------|------|------|
| `/game/api/interact` | POST | 角色交互（pat 等） |
| `/game/api/zones` | GET | 区域列表 |
| `/game/api/eco` | GET | 生态摘要 |
| `/game/api/emotions` | GET | 员工情绪状态 |
| `/game/api/relationships` | GET | 关系网络 |
| `/game/api/events` | GET | 事件日志（最近 50 条） |
| `/game/api/messages` | GET | 消息列表（最近 30 条） |
| `/game/api/memoir` | GET | 回忆录（最近 20 条） |

### 2.4 招募系统

| 端点 | 方法 | 说明 |
|------|------|------|
| `/game/api/recruit-status` | GET | 招募状态 |
| `/game/api/recruit` | POST | 开始招募 |

## 3. 负载均衡

Game Router 支持多服务器负载均衡：

```python
_server_loads: dict[str, float] = {}      # server_id -> 负载因子
_server_capacity: dict[str, int] = {}     # server_id -> 最大玩家数
_backup_servers: list[str] = []           # 备用服务器列表
```

## 4. 初始化

```python
from core.game_router import init_biosphere

# 在 web_server startup 中初始化
init_biosphere(biosphere_instance)
```

## 5. 前端页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 主游戏 | `/game/` | 2D 俯视角游戏界面 |
| 地图 | `/game/map` | 2.5D 地图 |
| 控制台 | `/game/console` | 极简控制台 |
| 报告 | `/game/report` | 进化报告 |
| 故事 | `/game/story` | 故事章节 |
| 快照 | `/game/snap` | 生态快照 |

## 6. 注意事项

- 生物圈实例通过 `init_biosphere` 注入，延迟初始化
- 所有 API 在生物圈未初始化时返回 503
- 前端页面通过 `game_frontend` / `console_frontend` 渲染
