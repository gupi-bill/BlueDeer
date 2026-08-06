# BlueDeer Tech Debt Audit

## 1. 大文件拆分（>20KB）

| 文件 | 大小 | 建议拆分 |
|------|------|----------|
| core/security.py | 33.8KB | SecurityScanner / SecurityGuard / SecurityReportGenerator 拆分为 3 个文件 |
| core/harness.py | 30KB | 调度 / 持久化 / 熔断重试 拆分为 3 个文件 |
| core/reward.py | 25.3KB | 奖励结算 / 排行榜 / 成就系统 拆分为 3 个文件 |
| core/healer.py | 25KB | 自愈策略 / 熔断器 / 重试 拆分为 3 个文件 |
| core/dream.py | 20.7KB | 梦境生成 / 记忆归档 / 质量评估 拆分为 3 个文件 |

## 2. 代码重复

- `core/agentic_loop.py`、`core/babyagi_loop.py`、`core/crewai_style.py`、`core/langgraph_style.py`、`core/agentgpt_style.py`、`core/opendevin_style.py` 均有重复的 prompt 构建和模型调用逻辑，应提取为 `core/llm_utils.py`。

## 3. 测试覆盖

- 当前 54 个测试全部通过，但 `core/agentic_loop.py`、`core/babyagi_loop.py`、`core/crewai_style.py`、`core/langgraph_style.py`、`core/agentgpt_style.py`、`core/opendevin_style.py` 无测试覆盖。
- 建议新增 `tests/test_007_agents.py` 覆盖 6 个 007 agent。

## 4. 安全扫描

- `core/security.py` 已有完善的 10 类静态扫描，建议接入 CI 流水线（pre-commit hook）。

## 5. 性能优化

- `core/task_orchestrator.py` 使用 ThreadPoolExecutor，可考虑 asyncio 化以提升并发性能。
