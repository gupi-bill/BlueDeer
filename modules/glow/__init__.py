import logging

logger = logging.getLogger(__name__)
"""BlueDeer Glow 发光渲染引擎模块。

融合 50 个跨平台 Glow/Agent 项目理念，为灵音雀、像素沙盘、各 Agent 提供统一发光渲染能力。

模块组成：
- color_downgrade.py：色板降级引擎（TrueColor→256→16→灰度 + CRT 滤镜叠加）
- role_glow.py：角色光晕系统（11 名员工 × 4 状态发光帧）
- alert_glow.py：告警分级光效（轻/中/重三级 + 专项色）
- task_graph_glow.py：任务链路发光图谱（TraceID 串联 + 报错脉冲 + 负载亮度）
"""
