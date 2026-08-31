"""第 12 层：工具接入 MCP 层。第一版占位，后续统一工具接口。"""

import logging

log = logging.getLogger(__name__)


class McpLayer:
    name = "mcp"

    def process(self, ctx):
        # TODO: 工具清单随配置加载，统一 MCP 接口
        log.info("[mcp] stub")
