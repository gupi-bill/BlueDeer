# EventBus 消息格式与生命周期

## 1. 消息格式

EventBus 使用 `core.task.Message` 作为标准消息载体，核心字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 消息唯一标识 |
| `trace_id` | `str` | 链路追踪 ID，关联上下游任务 |
| `topic` | `str` | 主题，支持通配符订阅，如 `agent.*` |
| `payload` | `dict[str, Any]` | 消息体，承载业务数据 |
| `created_at` | `float` | 创建时间戳（Unix 时间） |
| `priority` | `int` | 优先级，数字越大越优先处理 |

### 示例

```python
msg = Message(
    id="msg-001",
    trace_id="trace-abc",
    topic="agent.fox",
    payload={"action": "greet", "target": "squirrel"},
    priority=5,
)
```

## 2. 订阅规则

- 精确订阅：`bus.subscribe("agent.fox", handler)`
- 通配符订阅：`bus.subscribe("agent.*", handler)` 匹配 `agent.fox`、`agent.squirrel`
- 优先级：`priority` 数字越大越先执行，同优先级按插入顺序
- 过滤器：`filter=lambda msg: msg.payload.get("action") == "greet"`

## 3. 消息生命周期

```
publish(topic, message)
  ├─ 记录历史（最多 max_history 条）
  ├─ 匹配订阅者（精确 + 通配符）
  ├─ 按优先级排序
  ├─ 执行过滤器
  └─ 并发调用 handler（asyncio.gather）
       ├─ 成功：handler 正常返回
       ├─ 失败：记录 warning，继续其他 handler
       └─ 全部完成：publish 返回
```

## 4. 特殊发布模式

| 方法 | 说明 |
|------|------|
| `publish(topic, message)` | 标准发布，所有订阅者并发执行 |
| `publish_delayed(topic, message, delay)` | 延迟发布，`delay` 秒后执行 |
| `publish_with_retry(topic, message, max_retries)` | 带重试的发布，失败自动重试 |
| `publish_directed(topic, message, recipient)` | 定向发布，仅发给指定 handler |
| `request(task, assignee_topic, result_topic, timeout)` | 请求-响应模式，等待结果返回 |

## 5. 历史与重放

- `history(topic, limit)` 查看最近 N 条历史消息
- `replay(topic, count)` 重放最近 N 条消息给当前订阅者
- `publish_stats()` 返回各 topic 发布计数

## 6. 异常处理

- handler 抛出异常时，EventBus 记录 warning 并继续执行其他 handler
- 过滤器异常按“放行”处理，避免单点过滤失败导致消息丢失
- `publish_with_retry` 会对单个 handler 重试，最多 `max_retries` 次
