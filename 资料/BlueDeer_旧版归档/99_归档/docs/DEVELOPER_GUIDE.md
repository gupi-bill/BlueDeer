# BlueDeer 开发者快速入门

> 最后更新：2026-08-07

## 环境要求

- Python 3.11+ / 3.12
- Windows / macOS / Linux
- 虚拟环境（推荐）

## 快速开始

```bash
# 克隆仓库
git clone <repo-url>
cd BlueDeer

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Unix

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install pytest pytest-asyncio pytest-cov ruff black

# 运行测试
pytest tests/ -q

# 启动开发服务器
python -m uvicorn web_server:app --reload --port 8080
```

## 项目结构

```
BlueDeer/
├── core/                    # 核心运行时
│   ├── base_agent.py        # Agent 基类
│   ├── config.py            # 配置管理
│   ├── event_bus.py         # 事件总线
│   ├── security_guard.py    # 安全守卫
│   ├── api_server.py        # REST API
│   └── digital_life/        # 数字生命模块
├── web_server/              # FastAPI 仪表盘
│   ├── app.py               # 主应用
│   └── routes_*.py          # 路由拆分
├── modules/                 # 业务模块
│   ├── sparrow/             # 监控告警
│   ├── deer/                # 核心 Deer 实现
│   └── ...
├── tests/                   # 测试套件
│   ├── test_security_hardening.py  # 安全测试
│   ├── test_web_server.py          # Web 服务器测试
│   └── test_performance.py         # 性能基准
├── docs/                    # 文档
└── .github/workflows/       # CI/CD
```

## 核心概念

### Agent 系统

所有 Agent 继承 `BaseAgent`，实现 `_build_prompt` / `_self_check`。

```python
from core.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def _build_prompt(self, task):
        return f"处理任务: {task.description}"
```

### 事件总线

发布/订阅模式，支持重试与过滤。

```python
from core.event_bus import EventBus

bus = EventBus()
bus.subscribe("topic", handler)
bus.publish("topic", message)
```

### 安全守卫

CSRF、速率限制、输入验证一体化。

```python
from core.security_guard import get_security_guard

guard = get_security_guard()
if not guard.check_csrf(request):
    raise HTTPException(403)
```

## 开发规范

- 类型注解：所有公共方法必须标注
- 异常处理：禁止裸 `except: pass`，必须记录日志
- 线程安全：共享状态加锁
- 输入验证：使用 `core.input_validator`
- XSS 防护：HTML 输出必须转义

## 测试规范

```bash
# 全量测试
pytest tests/ -q

# 安全测试
pytest tests/test_security_hardening.py -v

# 性能测试
pytest tests/test_performance.py -v

# 覆盖率
pytest tests/ --cov=core --cov=web_server --cov-report=html
```

## 常见问题

**Q: 如何添加新的 Agent？**

A: 在 `core/digital_life/` 创建新文件，继承 `BaseAgent`，在 `agent_registry.py` 注册。

**Q: 如何添加新的路由？**

A: 在 `web_server/` 创建 `routes_<domain>.py`，在 `app.py` 中 `include_router`。

**Q: 安全加固流程？**

A: 见 `docs/SECURITY_REVIEW.md` 和 `tests/test_security_hardening.py`。

## 贡献指南

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing`)
5. 开启 Pull Request

## CI/CD

GitHub Actions 自动运行：
- ruff lint + black format check
- pytest 全量测试
- pip-audit CVE 扫描
- 覆盖率报告上传 Codecov
