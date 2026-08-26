# BlueDeer Agent

蓝鹿 Agent：按 13 层架构逐层推进的自主 AI Agent 骨架。

## 定位

第一版先跑通 13 层最小链路（输入 → 理解 → 记忆 → 决策 → 输出 + 监控日志），使用 Mock Provider，不接真实 LLM、零第三方依赖。后续再把 Ollama / SiliconFlow 等 provider 作为可插拔适配器接入。

## 快速启动

```bat
cd /d C:\Users\a\Desktop\vibe coding\BlueDeer-Agent
python -m bluedeer
```

或双击 `run.bat`。

退出：输入 `/exit`、`/quit` 或 `quit`。

## 测试

```bat
cd /d C:\Users\a\Desktop\vibe coding\BlueDeer-Agent
python -m unittest tests.smoke_test.py -v
```

## 目录结构

```text
BlueDeer-Agent/
├── bluedeer/
│   ├── __init__.py
│   ├── __main__.py        # python -m bluedeer 入口
│   ├── agent.py           # 核心循环编排
│   ├── config.py          # config.json 加载
│   ├── context.py         # 层间数据载体
│   ├── memory.py          # 进程内记忆
│   ├── providers.py       # Provider 抽象 + Mock
│   └── layers/            # 13 层，每层一个模块
│       ├── input.py
│       ├── understanding.py
│       ├── memory.py
│       ├── reasoning.py
│       ├── decision.py
│       ├── planning.py
│       ├── task_queue.py
│       ├── action.py
│       ├── result_check.py
│       ├── output.py
│       ├── safety.py
│       ├── mcp.py
│       └── monitoring.py
├── tests/
│   └── smoke_test.py
├── config.json
├── requirements.txt
├── run.bat
└── README.md
```

## 13 层开关

编辑 `config.json` 的 `layers` 字段，把对应层设为 `false` 即可关闭。任一层关闭，最小链路（输入 → 直答）仍成立。

## 密钥约定

密钥一律走环境变量，不写入 config.json。读取用 `bluedeer.config.get_env(key)`。
