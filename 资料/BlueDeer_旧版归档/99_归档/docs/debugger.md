# Debugger 断点与调试使用手册

## 1. 快速开始

```python
from core.debugger import Debugger
from core.tracer import Tracer

tracer = Tracer()
debugger = Debugger(tracer=tracer)
debugger.attach()

# ... 运行任务 ...

report = debugger.summary()
debugger.print_summary()
debugger.export_chrome_trace("logs/flame.json")
```

## 2. 断点管理

### 2.1 设置断点

```python
# 无条件断点
debugger.set_breakpoint()

# 条件断点（当 condition 为真时触发）
debugger.set_breakpoint(condition="task.status == 'failed'")
```

### 2.2 步进控制

```python
# 单步跳过（不进入子调用）
debugger.step_over()

# 单步进入（进入子调用）
debugger.step_into()

# 继续执行直到下一个断点
debugger.continue_execution()
```

## 3. 变量监视

```python
# 监视变量
debugger._watched_vars["counter"] = 0

# 获取变量值
value = debugger.watch_variable("counter")
```

## 4. Trace 摘要

### 4.1 生成摘要

```python
# 所有 trace
summaries = debugger.summary()

# 指定 trace
summaries = debugger.summary(trace_id="trace-abc")
```

### 4.2 摘要内容

每个 `TraceSummary` 包含：
- `trace_id`：链路 ID
- `total_duration_ms`：总耗时
- `span_count`：span 数量
- `agent_spans`：各组件 span 列表
- `errors`：错误列表
- `token_usage`：Token 使用量

### 4.3 打印摘要

```python
debugger.print_summary()
# 输出：
# ============================================================
# Trace: trace-abc
# Spans: 10 | Tokens: {'in': 100, 'out': 200}
#   harness: 2 spans, 15.2ms
#   agent.fox: 5 spans, 120.5ms
# ============================================================
```

## 5. 火焰图导出

```python
# 导出 Chrome Trace Event Format
path = debugger.export_chrome_trace("logs/flame.json")

# 在 Chrome 中打开：
# 1. 打开 chrome://tracing
# 2. 加载 flame.json
# 3. 查看火焰图
```

## 6. 使用场景

### 6.1 性能分析

```python
debugger.attach()
# ... 运行任务 ...
summary = debugger.summary()
for s in summary:
    for comp, spans in s.agent_spans.items():
        total_ms = sum(sp.duration_ms for sp in spans if sp.duration_ms > 0)
        print(f"{comp}: {total_ms:.1f}ms")
```

### 6.2 错误诊断

```python
summary = debugger.summary()
for s in summary:
    for e in s.errors:
        print(f"✗ {e.component}.{e.action}: {e.error}")
```

### 6.3 Token 消耗分析

```python
summary = debugger.summary()
for s in summary:
    print(f"Trace {s.trace_id}: {s.token_usage}")
```

## 7. 注意事项

- Debugger 需要在 Tracer 存在的情况下使用
- 默认不启用，需要调用 `enable()` 或 `attach()`
- 火焰图导出为 JSON 格式，兼容 Chrome Trace Viewer 和 Perfetto
- 断点条件为字符串表达式，需自行保证正确性
