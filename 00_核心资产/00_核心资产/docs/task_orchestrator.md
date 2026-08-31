# TaskOrchestrator 任务调度算法说明

## 1. 核心模型

TaskOrchestrator 基于 **DAG（有向无环图）** 进行任务编排：

- 每个任务是一个 `TaskNode`，包含名称、函数、依赖列表、结果、状态
- 依赖关系通过 `deps` 声明，例如 `merge` 依赖 `fetch_a` 和 `fetch_b`
- 执行前会进行 DAG 验证：检查依赖完整性和无环

## 2. 调度流程

```
run(timeout)
  ├─ 1. 验证 DAG（依赖完整性 + 无环检测）
  ├─ 2. 创建线程池（ThreadPoolExecutor，max_workers）
  └─ 3. 主循环：
       ├─ 检查超时
       ├─ 获取就绪任务（所有依赖已完成）
       ├─ 检查依赖失败（下游任务取消）
       ├─ 提交就绪任务到线程池
       ├─ 等待至少一个任务完成（as_completed）
       ├─ 更新任务状态（done/failed）
       └─ 重新检查就绪任务（可能触发新任务）
```

## 3. 关键特性

### 3.1 拓扑并行
- 所有依赖已完成的任务可以并行执行
- 依赖未完成的任务保持 pending 状态

### 3.2 失败传播
- 任务失败时，依赖它的下游任务自动取消
- 不会执行无效的计算

### 3.3 超时控制
- 支持全局超时，超时后所有 pending/running 任务标记为 cancelled
- 抛出 `TaskTimeoutError`

### 3.4 结果传递
- 依赖任务的结果按顺序传递给下游任务作为参数
- 例如：`merge(a_result, b_result)`

## 4. 状态机

```
pending -> running -> done
                -> failed -> (可重试)
                -> cancelled
                -> rolled_back
```

## 5. 重试机制

`retry_with_backoff` 支持指数退避重试：
- 第 1 次：等待 base_delay * 1
- 第 2 次：等待 base_delay * 2
- 第 3 次：等待 base_delay * 4
- 仅允许重试 `failed` 状态的任务

## 6. 回滚机制

`rollback_on_timeout` 支持超时回滚：
- 将超时任务及其下游 pending 任务标记为 `rolled_back`
- 防止部分成功、部分失败的中间状态

## 7. 复杂度

- 验证：O(V + E)，V=任务数，E=依赖数
- 调度循环：O(V * E)，每次迭代扫描所有任务
- 适合中小规模任务图（< 1000 任务）

## 8. 使用示例

```python
from core.task_orchestrator import TaskOrchestrator

orch = TaskOrchestrator(max_workers=4)
orch.add_task("fetch_a", lambda: fetch("a"))
orch.add_task("fetch_b", lambda: fetch("b"))
orch.add_task("merge", lambda a, b: merge(a, b), deps=["fetch_a", "fetch_b"])

results = orch.run(timeout=30.0)
merged = results["merge"]
```
