# Launchers 目录脚本使用说明

## 1. 目录概览

`launchers/` 目录包含 BlueDeer 集成栈的启动脚本、监控工具和自修复守护进程。

## 2. 启动脚本

### 2.1 启动全部集成.bat

- **用途**：一键启动整个 BlueDeer 集成栈
- **服务**：Odysseus + n8n + OpenClaw + OpenCode + Ollama
- **端口**：8000 / 5678 / 18789 / 4098 / 11434
- **用法**：双击运行

### 2.2 启动Ollama_GPU.bat

- **用途**：启动 Ollama 并启用 GPU 加速
- **环境变量**：
  - `OLLAMA_GPU_LAYERS=99`
  - `OLLAMA_FLASH_ATTENTION=1`
  - `OLLAMA_KEEP_ALIVE=-1`
- **用法**：双击运行

### 2.3 启动潜意识进化管线.bat

- **用途**：启动潜意识进化管线
- **用法**：双击运行

### 2.4 启动自修复.bat

- **用途**：启动自修复守护进程（selfheal.ps1）
- **行为**：后台隐藏运行，关闭窗口不退出
- **监控**：Ollama + 4 个 Web 服务，失败自动重启
- **用法**：双击运行

### 2.5 停止自修复.bat

- **用途**：停止自修复守护进程
- **行为**：根据 PID 杀死 selfheal 进程
- **用法**：双击运行

## 3. 监控工具

### 3.1 monitor_services.ps1

- **用途**：交互式监控 4 个服务状态
- **功能**：
  - 实时状态显示（UP/DOWN）
  - 日志文件大小跟踪
  - OpenClaw 保活自动重启
  - 键盘导航（1-4：查看日志/打开网页，l：日志模式，w：网页模式，q：退出）
- **用法**：在 PowerShell 中运行

## 4. 自修复系统

### 4.1 selfheal.ps1

- **用途**：后台守护进程，监控服务并自动重启失败的服务
- **循环间隔**：30 秒
- **监控服务**：Ollama、Odysseus、n8n、OpenClaw、OpenCode
- **特性**：
  - 指数退避重试
  - 单实例守护（mutex）
  - PID 文件跟踪
  - 优雅关闭支持

### 4.2 selfheal_hidden.vbs

- **用途**：隐藏窗口启动 selfheal.ps1
- **行为**：无控制台窗口运行 PowerShell 脚本

## 5. 启动脚本（launch_*.bat）

| 脚本 | 服务 | 端口 | 说明 |
|------|------|------|------|
| launch_1_odysseus.bat | Odysseus | 8000 | FastAPI 后端 |
| launch_2_n8n.bat | n8n | 5678 | 工作流自动化 |
| launch_3_openclaw.bat | OpenClaw | 18789 | 网关服务 |
| launch_4_opencode.bat | OpenCode | 4098 | Web 界面（缺失） |

### 启动行为
- 端口被占用时自动跳过
- 日志输出到 `logs/` 目录

## 6. 日志文件

所有日志存储在 `C:\Users\a\Desktop\vibe coding\logs\` 目录：
- `odysseus.log`
- `n8n.log`
- `openclaw.log`
- `selfheal.log`

## 7. 常见操作

### 7.1 启动全部服务

```batch
双击运行：启动全部集成.bat
```

### 7.2 仅启动 Ollama

```batch
双击运行：启动Ollama_GPU.bat
```

### 7.3 启动自修复守护

```batch
双击运行：启动自修复.bat
```

### 7.4 停止自修复

```batch
双击运行：停止自修复.bat
```

### 7.5 监控服务状态

```powershell
powershell -File monitor_services.ps1
```

## 8. 注意事项

- 部分脚本需要管理员权限
- 确保依赖服务（如 Node.js、Python）已安装
- 自修复守护进程会持续运行，需要手动停止
- OpenCode 启动脚本缺失（launch_4_opencode.bat），由 selfheal.ps1 直接处理
