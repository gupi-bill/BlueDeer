import logging
logger = logging.getLogger(__name__)
"""BlueDeer 外部集成渠道包。

零基础读者可以这样理解：
- 一个渠道 = 一种"打通外部世界"的方式（桌面通知、微信、邮件等）。
- 每个渠道模块都暴露一个 send(message_dict) 函数，统一接口。
- MessageRouter 根据消息优先级 + 用户配置，决定走哪些渠道。
"""
