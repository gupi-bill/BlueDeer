# Dream 梦境生成机制说明

## 1. 核心概念

DreamSystem 是 BlueDeer 的梦境记忆自主进化系统，模拟生物睡眠的四阶段流程：

1. **浅睡分拣**（LightSleep）：扫描任务结果，提取成功方案并评定质量
2. **REM 推演**（REMDream）：对方案做模拟优化
3. **深睡固化**（DeepSleep）：将优化方案写入向量库
4. **噩梦告警**（Nightmare）：检测重复失败模式

## 2. 四阶段流水线

### 2.1 浅睡分拣

- 扫描所有 TaskResult
- 提取成功任务的方案
- 评定记忆质量（NORMAL / HIGH / LEGENDARY）

质量评定规则：
- `HIGH`：代码行数 > quality_high_code_lines 或 token < quality_high_token
- `LEGENDARY`：代码行数 > quality_legendary_code_lines 且 token < quality_legendary_token

### 2.2 REM 推演

- 对提取的记忆进行模拟优化
- 生成改进后的方案
- 返回优化后的记忆列表

### 2.3 深睡固化

- 将优化后的记忆写入向量库
- 由调用方负责实际写入（解耦）
- 返回待固化记忆列表

### 2.4 噩梦告警

- 检测重复失败模式
- 同类错误出现超过阈值（默认 3 次）时触发告警
- 生成 NightmareAlert 记录

## 3. 记忆质量分级

| 等级 | 说明 | 检索优先级 |
|------|------|-----------|
| `NORMAL` | 普通记忆 | 正常 |
| `HIGH` | 高质量 | 优先 |
| `LEGENDARY` | 传奇 | 置顶 |

## 4. 记忆生命周期

- **过期归档**：超过 30 天（可配置）的记忆标记为过期
- **碎片清理**：内容过短且普通质量的记忆视为碎片
- **快照回滚**：支持回滚到之前的记忆状态

## 5. 使用方式

```python
from core.dream import DreamSystem

dream_system = DreamSystem(nightmare_threshold=3)
report, optimized = dream_system.dream(results, agent_id_map)

print(report.summary())
# 梦境阶段: complete
# 提取记忆: 5
# 优化记忆: 3
# 固化记忆: 3
# 质量分布: 普通=2 高质量=1 传奇=0
# 本轮节省 Token: 700
```

## 6. 跨岗位协同推演

- 支持多角色联动梦境
- 合并代码/美术/安全三方方案
- 通过 agent_id_map 标注记忆归属

## 7. 报告归档

- 每轮梦境自动生成 DreamReport
- 支持 Markdown 报告归档
- 包含质量分布统计和 nightmare 告警

## 8. 配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `nightmare_threshold` | 噩梦告警阈值 | 3 |
| `memory_archive_ttl` | 记忆过期时间（秒） | 30 天 |
| `fragile_min_len` | 碎片记忆最小长度 | 配置中 |
| `quality_high_code_lines` | HIGH 质量代码行数阈值 | 配置中 |
| `quality_high_token` | HIGH 质量 token 阈值 | 配置中 |
| `quality_legendary_code_lines` | LEGENDARY 代码行数阈值 | 配置中 |
| `quality_legendary_token` | LEGENDARY token 阈值 | 配置中 |

## 9. 注意事项

- 梦境系统不直接写入向量库，由调用方负责固化
- 噩梦阈值可动态调整
- 高质量记忆可计入 reward 系统
