"""灵音雀 VoiceSparrowAgent 模块：双形态全局状态播报员。

模块组成：
- status_center.py：状态查询中心，聚合 7 大类系统数据
- agent.py：VoiceSparrowAgent 双形态（UI 内嵌 + 后台值守）
- announcer.py：自动巡检播报器（定时简报 + 异常告警 + 节点播报）
- logs/：巡检简报与告警历史持久化
"""
