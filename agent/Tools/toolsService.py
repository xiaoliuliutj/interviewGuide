"""Agent 可调用工具的注册与可靠执行入口。"""

import asyncio
import json

from agent.Common.AgentModels import AgentContext, ToolCall, ToolExecutionResult
from agent.Common.Exceptions.AgentException import AgentException, ToolArgumentError, ToolExecutionError, ToolNotRegisteredError, ToolTimeoutError
from agent.Tools.toolsDocumentParser.toolsDocumentParser import ToolsDocumentParser
from agent.Tools.toolsWebReader.toolsWebReader import WebReader
from agent.Tools.toolsWebsiteCrawler.toolsWebsiteCrawler import ToolsWebsiteCrawler


class ToolService:
    """注册文档解析、网页读取和网站爬取工具，并提供统一的超时与异常处理。"""

    def __init__(self, timeoutSeconds: int = 60) -> None:
        """建立工具注册表，所有工具共享同一执行超时上限。"""
        reader = WebReader()
        parser = ToolsDocumentParser()
        crawler = ToolsWebsiteCrawler(reader)
        self.timeoutSeconds = timeoutSeconds
        self.tools = {
            "parseDocument": parser.parseDocument,
            "fetchWebPage": self.fetchWebPage,
            "crawlWebPages": crawler.crawlWebPages,
        }
        self.webReader = reader

    async def fetchWebPage(self, arguments: dict, _: AgentContext) -> dict:
        """校验地址后读取单个公开网页。"""
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ToolArgumentError("fetchWebPage 需要非空 url")
        return await self.webReader.fetchPage(url.strip())

    async def executeTool(self, toolCall: ToolCall, context: AgentContext) -> ToolExecutionResult:
        """在限定时间内执行已授权工具，并保持领域错误码不被重新包装。"""
        handler = self.tools.get(toolCall.name)
        if handler is None:
            raise ToolNotRegisteredError(f"工具 {toolCall.name} 未注册")
        try:
            data = await asyncio.wait_for(
                handler(toolCall.arguments, context),
                timeout=self.timeoutSeconds,
            )
        except TimeoutError as error:
            raise ToolTimeoutError(f"工具 {toolCall.name} 执行超时") from error
        except AgentException:
            raise
        except Exception as error:
            raise ToolExecutionError(f"工具 {toolCall.name} 执行失败：{error}") from error
        return ToolExecutionResult(
            name=toolCall.name,
            content=json.dumps(data, ensure_ascii=False),
            succeeded=True,
        )
