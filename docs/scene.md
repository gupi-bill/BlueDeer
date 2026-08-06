# Scene 场景管理最佳实践

## 1. 核心概念

CEOOffice 是 BlueDeer 的全局调度中心，整合所有办公空间：

| 空间 | 说明 |
|------|------|
| Library | 资料库，知识中心 |
| BreakRoom | 茶水间，员工交流区 |
| OfficeManager | 办公室，员工个人空间 |
| RestArea | 休息区，放松回顾区 |

## 2. 初始化

```python
from core.scene import CEOOffice
from core.library import Library
from core.breakroom import BreakRoom
from core.office import OfficeManager
from core.restarea import RestArea

ceo_office = CEOOffice(
    library=Library(),
    breakroom=BreakRoom(),
    office_manager=OfficeManager(),
    rest_area=RestArea(),
)
```

## 3. 场景切换

### 3.1 切换场景

```python
# 切换到指定场景
result = ceo_office.transition_to("library", effect="fade")
# 返回 {"from": "office", "to": "library", "effect": "fade"}
```

### 3.2 场景栈

```python
# 压入场景
ceo_office.push_scene("breakroom")

# 弹出场景
prev = ceo_office.pop_scene()
```

### 3.3 当前场景

```python
current = ceo_office.get_current_scene()
```

## 4. 全场景状态

```python
# 获取全场景状态
status = ceo_office.status()
# {
#     "library": {...},
#     "breakroom": {...},
#     "offices": {...},
#     "rest_area": {...}
# }
```

## 5. 导出数据

```python
# 导出全场景数据
data = ceo_office.to_dict()
```

## 6. 会议管理

```python
# 召开会议
meeting = ceo_office.hold_meeting(
    topic="代码审查",
    participants=["fox", "squirrel"],
)
# {
#     "meeting_id": "mtg_...",
#     "topic": "代码审查",
#     "participants": ["fox", "squirrel"],
#     "announcement_id": "..."
# }
```

## 7. 过渡效果

支持两种过渡效果：

| 效果 | 说明 |
|------|------|
| `fade` | 淡入淡出 |
| `slide` | 滑动切换 |

## 8. 最佳实践

### 8.1 场景栈管理
- 使用 `push_scene` / `pop_scene` 管理场景栈
- 避免直接操作 `_scene_stack`

### 8.2 状态查询
- 优先使用 `status()` 获取摘要
- 使用 `to_dict()` 进行持久化

### 8.3 会议广播
- 会议通过 BreakRoom.announce 广播
- 参会者通过 BreakRoom 接收消息

## 9. 注意事项

- 场景栈至少保留一个场景（不能清空）
- 过渡效果目前仅记录，实际动画由前端实现
- 会议 ID 基于时间戳生成，确保唯一性
