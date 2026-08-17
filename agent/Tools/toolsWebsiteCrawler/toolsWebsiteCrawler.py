from typing import Any

from agent.Common.AgentModels import AgentContext
from agent.Common.Exceptions.AgentException import ToolArgumentError
from agent.Tools.toolsWebReader.toolsWebReader import WebReader


class ToolsWebsiteCrawler:
    """提供模型按需调用的同域网站爬取工具。"""

    def __init__(self, webReader: WebReader) -> None:
        """复用网页读取工具的安全校验与页面抓取能力。"""
        self.webReader = webReader

    async def crawlWebPages(self, arguments: dict[str, Any], _: AgentContext) -> dict[str, Any]:
        """从给定入口开始抓取限定深度的同域页面。"""
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ToolArgumentError("crawlWebPages 需要非空 url")
        return await self.webReader.crawlSite(url.strip())
