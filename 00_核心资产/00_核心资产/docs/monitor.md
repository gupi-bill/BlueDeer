# Monitor 指标采集与告警配置文档

## 1. 核心概念

SystemMonitor 负责：
- 定期采集系统资源指标（CPU、内存、磁盘）
- 执行健康检查（Harness、磁盘、临时目录）
- 评估告警规则并触发通知

## 2. 指标采集

### 2.1 内置指标

| 指标 | 说明 | 单位 |
|------|------|------|
| `cpu_percent` | CPU 使用率 | % |
| `memory_percent` | 内存使用率 | % |
| `disk_percent` | 磁盘使用率 | % |

### 2.2 采集方式

```python
monitor = SystemMonitor(check_interval=60.0)

# 手动采集
usage = monitor.resource_usage()
print(usage["cpu_percent"])
print(usage["memory_percent"])
print(usage["disk"]["percent"])
```

### 2.3 自定义指标

```python
# 推送自定义指标
monitor.push_metric("request_latency", 0.123)

# 聚合查询（滚动窗口）
stats = monitor.aggregate("request_latency", window=300)
# 返回 {min, max, avg, median, count, last}
```

## 3. 健康检查

### 3.1 内置检查项

| 检查项 | 说明 |
|--------|------|
| `harness` | Harness 服务状态 |
| `disk` | 磁盘空间（剩余 < 0.5GB 为 degraded） |
| `temp_dir` | 临时目录可写性 |

### 3.2 执行检查

```python
statuses = monitor.check_services()
for s in statuses:
    print(f"{s.service}: {s.status} (latency: {s.latency_ms}ms)")
```

## 4. 告警规则

### 4.1 默认阈值

| 指标 | 警告阈值 | 严重阈值 |
|------|----------|----------|
| CPU | > 90% | - |
| 内存 | > 85% | - |
| 磁盘 | - | > 90% |

### 4.2 自定义告警

通过 `AlertEngine` 注册自定义规则：

```python
from core.alert import get_alert_engine

engine = get_alert_engine()
engine.add_rule(
    rule_id="high-cpu",
    metric="cpu_percent",
    threshold=90,
    severity="warning",
    message="CPU 使用率过高",
)
```

### 4.3 告警评估

```python
# 评估所有规则
alerts = monitor.check_thresholds()
for a in alerts:
    print(f"[{a['severity']}] {a['rule_name']}: {a['message']}")
```

### 4.4 快速评估

```python
# 使用默认阈值快速评估
alerts = monitor.evaluate_alerts(usage)
```

## 5. 后台监控

```python
# 启动后台监控循环
await monitor.start()

# 停止
await monitor.stop()

# 查看历史
history = monitor.get_history(limit=10)
```

## 6. 历史记录

- 最多保留 100 条历史记录（可配置 `_max_history`）
- 每条记录包含：timestamp、usage、alerts

## 7. 注意事项

- 需要 `psutil` 库才能采集 CPU/内存指标，否则返回 0.0
- 健康检查的磁盘阈值（0.5GB）硬编码在 `check_disk` 中
- 告警规则通过 `AlertEngine` 统一管理，支持持久化
