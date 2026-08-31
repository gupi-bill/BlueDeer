# BlueDeer 外部集成配置指南

> 本文档面向零基础读者，介绍 BlueDeer 智能体如何对接真实的外部环境（Git、Shell、API）。
> 第十四阶段（commit 39）新增能力。

## 一、整体设计

智能体默认在"内部模拟"环境中工作，所有操作都是虚拟的，不会影响真实文件系统。
通过开启"外部集成"，智能体可以直接操作真实的 Git 仓库、执行 shell 命令、调用外部 API。

### 三种外部集成

| 集成 | 风险等级 | 说明 | 默认状态 |
|------|---------|------|---------|
| Git 集成 | 🟡 中 | 海狸执行真实 git 提交、分支管理 | 关闭 |
| Shell 执行 | 🔴 高 | 智能体执行白名单内的 shell 命令 | 关闭 |
| 外部 API | 🟢 低 | 调用用户配置的 HTTP/HTTPS API | 关闭 |

### 安全原则

1. **默认全部关闭** —— 必须显式开启才能使用
2. **写操作需审批** —— 创建/修改/删除类操作必须监工批准
3. **白名单/黑名单** —— Shell 命令双名单机制，禁止危险命令
4. **超时保护** —— 所有命令有超时限制（默认 60 秒）
5. **密钥不进日志** —— API 密钥只存配置文件，日志中自动脱敏
6. **完整审计** —— 所有操作记录到历史，可追溯

---

## 二、配置文件

配置文件路径：`data/external_config.json`

首次启动时自动创建，结构如下：

```json
{
  "git": {
    "enabled": false,
    "repo_path": "",
    "require_approval": true,
    "allow_dangerous": false
  },
  "shell": {
    "enabled": false,
    "whitelist": ["python", "pytest", "npm", "node", "git", "ls", "echo", "cat"],
    "blacklist": ["rm -rf", "sudo", "chmod 777", "curl", "wget"],
    "timeout": 60,
    "workdir": "/workspace",
    "require_approval": true
  },
  "api": {
    "enabled": false,
    "require_approval": true,
    "endpoints": []
  }
}
```

### 字段说明

#### git 节

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用 Git 集成 |
| `repo_path` | string | Git 仓库路径（绝对路径） |
| `require_approval` | bool | 是否需要监工审批（默认 true） |
| `allow_dangerous` | bool | 是否允许危险操作如 `push --force`（默认 false） |

#### shell 节

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用 Shell 集成 |
| `whitelist` | list | 允许执行的命令前缀（如 `python`、`git`） |
| `blacklist` | list | 禁止执行的命令片段（如 `rm -rf`、`sudo`） |
| `timeout` | int | 超时秒数（默认 60） |
| `workdir` | string | 工作目录（默认 `/workspace`） |
| `require_approval` | bool | 是否需要监工审批（默认 true） |

#### api 节

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用 API 集成 |
| `require_approval` | bool | 是否需要监工审批（GET 类默认放行，POST/PUT/DELETE 需审批） |
| `endpoints` | list | 预配置的 API 端点列表 |

`endpoints` 每项结构：

```json
{
  "name": "github_api",
  "url": "https://api.github.com",
  "auth_type": "token",
  "auth_value_env": "GITHUB_TOKEN",
  "default_headers": {
    "Accept": "application/vnd.github.v3+json"
  }
}
```

---

## 三、前端操作

### 打开外部集成面板

- 点击顶部导航栏的 **🔌外部** 按钮
- 或按键盘 **E** 键

### 三个 Tab

#### 1. 配置 Tab

每个集成一个开关，点击 checkbox 即可开启/关闭。
高级配置（仓库路径、白名单、API 密钥等）请直接编辑 `data/external_config.json`。

#### 2. 审批 Tab

显示所有待审批的外部操作：

- 操作类型（git / shell / api）
- 发起智能体
- 操作摘要和详情
- 风险等级（🟢 低 / 🟡 中 / 🔴 高）
- 创建时间

每条审批有 **✓ 批准** 和 **✗ 拒绝** 两个按钮。

#### 3. 执行 Tab

提供快速执行按钮（用于演示和测试）：

- **Git status** —— 查看仓库状态
- **Git log** —— 查看最近 5 条提交
- **python --version** —— 查看 Python 版本
- **git --version** —— 查看 Git 版本

下方显示各集成的当前状态。

### 顶部审批铃铛

顶部导航栏的 **🔔** 图标显示待审批数量（红点 + 数字）。
点击打开审批队列面板。

---

## 四、API 接口

所有 API 都需要登录（cookie 鉴权）。

### 1. 配置管理

#### GET /api/external/config

返回当前配置（密钥字段已脱敏）。

**响应**：

```json
{
  "config": {
    "git": {"enabled": false, "repo_path": "", "require_approval": true, ...},
    "shell": {"enabled": true, "whitelist": [...], ...},
    "api": {"enabled": false, ...}
  }
}
```

#### POST /api/external/config

更新某一节配置。

**请求体**：

```json
{
  "section": "shell",
  "config": {
    "enabled": true,
    "whitelist": ["python", "git"],
    "blacklist": ["rm -rf"],
    "timeout": 60,
    "require_approval": true
  }
}
```

**响应**：

```json
{"ok": true}
```

### 2. 状态查询

#### GET /api/external/status

返回各集成的运行状态。

**响应**：

```json
{
  "status": {
    "git": {"enabled": false, "repo_path": "", "require_approval": true, "repo_exists": false},
    "shell": {"enabled": true, "whitelist": [...], "timeout": 60.0, "workdir": "/workspace"},
    "api": {"enabled": false, "endpoints": []},
    "pending_approvals": 0
  }
}
```

### 3. 执行操作

#### POST /api/external/execute

执行一次外部操作。

**请求体**：

```json
{
  "op_type": "shell",
  "params": {
    "command": "python --version",
    "summary": "查看 Python 版本",
    "risk_level": "low"
  }
}
```

`op_type` 取值：
- `git` —— `params.args` 是 git 命令参数列表，如 `["status"]` 或 `["log", "--oneline", "-5"]`
- `shell` —— `params.command` 是完整 shell 命令字符串
- `api` —— `params.endpoint`/`method`/`path`/`query`/`body` 等

**响应（需审批时）**：

```json
{
  "ok": false,
  "pending_approval": "ap-xxxxxxxx",
  "summary": "查看 Python 版本",
  "message": "等待监工审批",
  "kind": "approval",
  "decision": "pending"
}
```

**响应（直接执行时）**：

```json
{
  "ok": true,
  "command": "python --version",
  "stdout": "Python 3.14.4\n",
  "stderr": "",
  "returncode": 0,
  "duration_ms": 10.61,
  "kind": "result"
}
```

### 4. 审批管理

#### GET /api/external/approvals

返回待审批列表。

**响应**：

```json
{
  "pending": [
    {
      "id": "ap-xxxxxxxx",
      "op_type": "shell",
      "agent_id": "supervisor",
      "agent_name": "监工",
      "species": "supervisor",
      "summary": "查看 Python 版本",
      "detail": {"command": "python --version"},
      "risk_level": "medium",
      "created_ts": 1784637028.42,
      "decision": "",
      "result": {}
    }
  ]
}
```

#### POST /api/external/approvals

审批一条操作。

**请求体**：

```json
{
  "id": "ap-xxxxxxxx",
  "decision": "approved",
  "reason": "测试批准"
}
```

`decision` 取值：`approved` / `rejected`

**响应（批准时）**：

```json
{
  "ok": true,
  "result": {
    "ok": true,
    "command": "python --version",
    "stdout": "Python 3.14.4\n",
    "returncode": 0,
    "duration_ms": 10.61
  },
  "decision": "approved"
}
```

---

## 五、典型使用流程

### 场景 1：让海狸执行真实的 git 提交

1. 在 `data/external_config.json` 中配置 `git.repo_path` 指向你的仓库
2. 前端打开 **🔌外部** 面板，开启 Git 集成
3. 海狸写完代码后调用 `tool_executor.execute_external(agent, "git", {args: ["add", "."], summary: "提交代码"})`
4. 监工在审批队列中看到请求，点击 **✓ 批准**
5. 海狸继续执行 `git commit -m "xxx"` 和 `git push`

### 场景 2：让松鼠运行单元测试

1. 前端开启 Shell 集成
2. 在白名单中加入 `pytest`
3. 松鼠调用 `tool_executor.execute_external(agent, "shell", {command: "pytest tests/", summary: "运行测试"})`
4. 监工审批通过后，测试结果返回给松鼠
5. 松鼠根据测试结果调整代码

### 场景 3：调用 GitHub API

1. 在 `data/external_config.json` 的 `api.endpoints` 中配置：

```json
{
  "name": "github",
  "url": "https://api.github.com",
  "auth_type": "token",
  "auth_value_env": "GITHUB_TOKEN",
  "default_headers": {"Accept": "application/vnd.github.v3+json"}
}
```

2. 设置环境变量：`export GITHUB_TOKEN=ghp_xxxxxxxx`
3. 前端开启 API 集成
4. 智能体调用 `tool_executor.execute_external(agent, "api", {endpoint: "github", method: "GET", path: "user/repos"})`
5. GET 类请求默认放行（可在配置中改为需审批）

---

## 六、安全建议

### 1. 最小权限原则

- 只开启实际需要的集成
- Shell 白名单只放必要的命令
- Git 仓库路径限定到特定项目目录
- API 端点限定到必要的域名

### 2. 密钥管理

- API 密钥通过环境变量传递（`auth_value_env` 字段）
- 配置文件中只存环境变量名，不存实际密钥
- 日志中自动脱敏（`redacted: true` 标记）

### 3. 审批习惯

- 高风险操作（🔴）必须人工审批
- 中风险操作（🟡）建议人工审批
- 低风险操作（🟢）可设置自动放行
- 定期检查审批历史，发现异常操作

### 4. 危险命令防护

Shell 黑名单默认包含：

- `rm -rf` —— 递归删除
- `sudo` —— 提权操作
- `chmod 777` —— 危险权限
- `curl` / `wget` —— 网络下载

可根据需要添加更多危险命令。

---

## 七、故障排查

### 问题 1：开启集成后操作没反应

**原因**：可能是配置未生效。

**解决**：
1. 检查 `data/external_config.json` 是否正确
2. 重启 game_server
3. 查看 `/api/external/status` 确认 `enabled` 字段

### 问题 2：审批后命令执行失败

**原因**：可能是白名单未包含该命令，或超时。

**解决**：
1. 查看返回的 `error` 字段
2. 检查 `whitelist` 是否包含命令前缀
3. 增加 `timeout` 值

### 问题 3：Git 操作报"not a git repository"

**原因**：`repo_path` 指向的目录不是 Git 仓库。

**解决**：
1. 确认路径正确
2. 在该目录执行 `git init`（如果是新仓库）
3. 检查目录权限

### 问题 4：API 调用报 401

**原因**：认证失败。

**解决**：
1. 检查环境变量是否设置（`echo $GITHUB_TOKEN`）
2. 检查 `auth_value_env` 字段名是否正确
3. 确认 token 未过期

---

## 八、相关文件

| 文件 | 说明 |
|------|------|
| `core/digital_life/external/external_manager.py` | 外部集成总控（单例） |
| `core/digital_life/external/git_integration.py` | Git 操作封装 |
| `core/digital_life/external/shell_executor.py` | Shell 命令执行 |
| `core/digital_life/external/api_caller.py` | 外部 API 调用 |
| `core/digital_life/tool_executor.py` | 工具执行沙箱（含 `execute_external`） |
| `game_server.py` | Web 服务器（含外部集成 API） |
| `game_frontend.py` | 前端 UI（外部集成面板） |
| `data/external_config.json` | 配置文件（运行时生成） |
| `data/external_approvals.json` | 审批历史（运行时生成） |

---

## 九、零依赖说明

外部集成全部使用 Python 标准库：

- Git 操作：通过 `subprocess` 调用系统 `git` 命令
- Shell 执行：通过 `subprocess` 执行命令
- API 调用：通过 `urllib.request` 发送 HTTP 请求

不引入任何第三方依赖，保持项目零依赖特性。
