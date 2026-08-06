# BlueDeer Next Sprint Plan

## Completed (006 series)
- [x] 006-1: Audit todo list
- [x] 006-2: Review project structure
- [x] 006-3: Check test infrastructure
- [x] 006-4: Security posture review
- [x] 006-5: Tech debt audit
- [x] 006-6: Document architecture
- [x] 006-006: Core architecture梳理
- [x] 007-AutoGPT: agentic loop implementation
- [x] 007-BabyAGI: 3-agent loop implementation
- [x] 007-CrewAI: role-based crew implementation
- [x] 007-LangGraph: state graph implementation
- [x] 007-AgentGPT: goal-driven agent implementation
- [x] 007-OpenDevin: dev loop implementation
- [x] 008-8: benchmark suite (scripts/benchmark_agent_loops.py)
- [x] P0-1: 007 Agent Integration (FrameworkAgent + Harness/EventBus)
- [x] P0-2: Test Coverage (test_007_agents.py / test_008_integration.py)
- [x] P0-3: Bug Fixes (30 files syntax errors fixed, 183 tests green)
- [x] P1-1: LangGraph Checkpoint (StateGraph checkpoint persistence)
- [x] P1-2: BabyAGI Memory (vector_db integration)
- [x] P1-3: CrewAI Flow (EventBus-based state machine)

## Next Sprint Priorities

### P0 (Next Sprint)
- [x] 1. **007 Agent Integration**: Connect all 6 agents to Harness/EventBus
- [x] 2. **Test Coverage**: Add integration tests for 007 agents
- [x] 3. **Bug Fixes**: Address any issues found in testing

### P1 (Following Sprint)
- [x] 1. **LangGraph Checkpoint**: Persist StateGraph checkpoints to disk
- [x] 2. **BabyAGI Memory**: Replace placeholder with vector_db
- [x] 3. **CrewAI Flow**: EventBus-based state machine

### P2 (Backlog)
- [x] 1. **Large File Refactoring**: Split healer.py, dream.py, security.py
- [x] 2. **Async Orchestrator**: Convert TaskOrchestrator to asyncio
- [x] 3. **CI Pipeline**: Add pre-commit hooks for security scanning

## Next Sprint (009 series)，2026-08-06 完成

- [x] 009-1: 编写 BlueDeer 总系统提示词 `BlueDeer/SYSTEM_PROMPT.md`（9 章，纯中文，给新接手 AI / 云端 Trae 当 context）
- [x] 009-2: 编写 OpenCode 超长系统提示词 `BlueDeer/OPENCODE_SYSTEM_PROMPT.md`（16 章），已配入 `opencode.json` 的 `instructions` 数组最前
- [x] 009-3: Kilo / OpenCode 免权限一键配置（`tools/kilo_autoallow.py` + `tools/kilo_allow_all.bat`），5 个配置文件全放行，保留删 D 盘等红线 deny
- [x] 009-4: Kilo token 用量统计器（`tools/kilo_usage.py`，单位中文亿/万），多窗口共库天然汇总
- [x] 009-5: 建立 Bill 知识库 BlueDeer 区（README + 操作规范 + 索引更新），原目录缺失已补建
- [x] 009-6: 测试基线确认 BlueDeer 全套 pytest 299 passed（约 2.8s）

## 待办，需对齐

- [ ] 010-1: 重构 `game_frontend.py`（13165 行，前端 HTML/CSS/JS 以 Python 字符串内嵌）。涉及从单文件自包含改为外部模板文件的架构调整，需先与用户对齐方案再动
- [ ] 010-2: 清理工作区冗余目录（`.cleanup_backup/` 等），删前需列影响范围加回收站备份，等用户授权
