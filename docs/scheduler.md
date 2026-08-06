# Scheduler 定时任务配置指南

## 1. 定时任务定义

定时任务通过 `JobDef` 定义，支持两种触发模式：

### 1.1 Cron 模式

使用标准 6 段 cron 表达式：`秒 分 时 日 月 周`

```python
from core.scheduler import JobDef

job = JobDef(
    id="hourly-cleanup",
    cron="0 0 * * * *",  # 每小时整点
    task_type="cleanup",
    task_payload={"max_age": 3600},
    assignee="cleaner-agent",
    description="每小时清理过期数据",
)
```

### 1.2 固定间隔模式

使用 `interval_seconds` 替代 cron，按固定间隔运行：

```python
job = JobDef(
    id="health-check",
    interval_seconds=60,  # 每 60 秒
    task_type="health",
    task_payload={},
    description="每分钟健康检查",
)
```

## 2. 定时任务字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `str` | 是 | 任务唯一标识 |
| `cron` | `str` | 否 | 6 段 cron 表达式 |
| `interval_seconds` | `int` | 否 | 固定间隔秒数，>0 时生效 |
| `task_type` | `str` | 否 | 任务类型，默认 `general` |
| `task_payload` | `dict` | 否 | 任务参数 |
| `assignee` | `str` | 否 | 执行代理 |
| `enabled` | `bool` | 否 | 是否启用，默认 True |
| `description` | `str` | 否 | 任务描述 |

## 3. Cron 表达式格式

标准 6 段 cron：`秒 分 时 日 月 周`

每段支持以下格式：
- `*`：任意值
- `5`：指定值
- `1-5`：范围
- `*/5`：步长
- `1,3,5`：列表
- `1-10/2`：范围 + 步长

### 常用示例

| 表达式 | 说明 |
|--------|------|
| `0 0 * * * *` | 每小时整点 |
| `0 0 9 * * *` | 每天 9:00 |
| `0 0 9 * * 1-5` | 工作日 9:00 |
| `0 */5 * * * *` | 每 5 分钟 |
| `0 0 1 1 * *` | 每年 1 月 1 日 |

## 4. 任务管理

### 4.1 添加任务

```python
scheduler = Scheduler(event_bus, harness)
job_id = scheduler.add_job(job)
```

### 4.2 删除任务

```python
ok = scheduler.remove_job("hourly-cleanup")
```

### 4.3 列出任务

```python
jobs = scheduler.list_jobs()
# 返回 {job_id: JobDef}
```

### 4.4 启停调度器

```python
await scheduler.start()   # 启动后台 tick 循环
await scheduler.stop()    # 停止调度
```

## 5. 持久化

- 任务自动保存到 `data/scheduler_jobs.json`
- 重启后自动恢复
- 支持 `load_jobs()` / `save_jobs()` 手动操作

## 6. 注意事项

- cron 和 interval_seconds 不能同时设置
- 任务执行失败不影响其他任务调度
- 任务执行时间超过间隔时，会在下次 tick 时跳过（避免堆积）
- 调度精度为 1 分钟（默认 tick 间隔）
