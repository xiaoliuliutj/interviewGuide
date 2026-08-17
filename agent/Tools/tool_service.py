"""Agent 可调用工具的注册表和执行边界。"""

import asyncio
import base64
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from agent.Agents.models import AgentContext, ToolCall, ToolExecutionResult
from agent.Common.Exceptions.agent_exception import (
    AgentException,
    ToolArgumentError,
    ToolExecutionError,
    ToolNotRegisteredError,
    ToolTimeoutError,
)
from agent.Memory.memory_service import MemoryService
from agent.RAG.document_parser import DocumentParser
from agent.RAG.rag_service import RagService
from agent.Tools.web_reader import WebReader


ToolHandler = Callable[[dict[str, Any], AgentContext], Awaitable[dict[str, Any]]]


class ToolService:
    """维护工具名称到真实业务函数的映射，并向 ReAct Loop 返回统一文本结果。"""

    def __init__(
        self,
        memoryService: MemoryService,
        ragService: RagService,
        webReader: WebReader | None = None,
        timeoutSeconds: int = 60,
    ) -> None:
        """注入已有领域服务；注册表只负责调度，不复制 Memory、RAG 或网页处理业务。"""
        self.memoryService = memoryService
        self.ragService = ragService
        self.webReader = webReader or WebReader()
        self.timeoutSeconds = timeoutSeconds
        self.handlers: dict[str, ToolHandler] = {
            "loadMemory": self.loadMemory,
            "retrieveKnowledge": self.retrieveKnowledge,
            "fetchWebPage": self.fetchWebPage,
            "crawlWebPages": self.crawlWebPages,
            "parseDocument": self.parseDocument,
            "getKnowledgeBaseStatus": self.getKnowledgeBaseStatus,
        }

    async def executeTool(
        self,
        toolCall: ToolCall,
        context: AgentContext,
    ) -> ToolExecutionResult:
        """按模型给出的名称调用已注册工具，并把领域结果序列化为下一轮可读取的 Tool 消息。"""
        handler = self.handlers.get(toolCall.name)
        if handler is None:
            raise ToolNotRegisteredError(f"工具 {toolCall.name} 未注册")
        try:
            payload = await asyncio.wait_for(
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
            content=json.dumps(payload, ensure_ascii=False),
            succeeded=True,
        )

    async def loadMemory(
        self,
        _: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """读取当前会话可见的短期与长期记忆，供模型在需要时重新聚焦上下文。"""
        messages = await self.memoryService.loadMemory(context)
        return {
            "messages": [
                {"role": item.role, "content": item.content}
                for item in messages
            ],
        }

    async def retrieveKnowledge(
        self,
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """使用模型指定的查询词执行已有混合检索，复用 RAG 的权限、缓存和来源追踪逻辑。"""
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolArgumentError("retrieveKnowledge 需要非空 query")
        requestData = dict(context.request.data)
        requestData["query"] = query.strip()
        request = context.request.model_copy(update={"data": requestData})
        retrievalContext = replace(context, request=request)
        items = await self.ragService.retrieveKnowledge(retrievalContext)
        return {"query": query.strip(), "documents": items}

    async def fetchWebPage(
        self,
        arguments: dict[str, Any],
        _: AgentContext,
    ) -> dict[str, Any]:
        """抓取单个公开网页并提取正文，返回可直接用于回答或知识入库的 Markdown。"""
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ToolArgumentError("fetchWebPage 需要非空 url")
        return await self.webReader.fetchPage(url.strip())

    async def crawlWebPages(
        self,
        arguments: dict[str, Any],
        _: AgentContext,
    ) -> dict[str, Any]:
        """从入口网页在同域名内进行有限深度抓取，适用于将一组页面交给后续知识库入库流程。"""
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ToolArgumentError("crawlWebPages 需要非空 url")
        return await self.webReader.crawlSite(url.strip())

    async def parseDocument(
        self,
        arguments: dict[str, Any],
        _: AgentContext,
    ) -> dict[str, Any]:
        """解析上传文档为保留标题与页码的文本段落，供需要展示或排查解析结果的任务使用。"""
        content = arguments.get("content")
        fileName = arguments.get("fileName")
        if not isinstance(content, str) or not isinstance(fileName, str) or not fileName.strip():
            raise ToolArgumentError("parseDocument 需要 content 和 fileName")
        try:
            raw = base64.b64decode(content) if arguments.get("contentEncoding") == "base64" else content.encode("utf-8")
        except Exception as error:
            raise ToolArgumentError("parseDocument 的 Base64 内容无效") from error
        parser = DocumentParser()
        contentType = arguments.get("contentType")
        sections = parser.parse(raw, fileName, contentType if isinstance(contentType, str) else None)
        return {
            "sections": [
                {
                    "content": section.content,
                    "headingPath": section.headingPath,
                    "pageNumber": section.pageNumber,
                }
                for section in sections
            ],
        }

    async def getKnowledgeBaseStatus(
        self,
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """查询调用主体可访问知识库的索引状态，避免模型根据过期上下文臆测可用性。"""
        knowledgeBaseId = arguments.get("knowledgeBaseId")
        if not isinstance(knowledgeBaseId, str) or not knowledgeBaseId.strip():
            raise ToolArgumentError("getKnowledgeBaseStatus 需要 knowledgeBaseId")
        return await self.ragService.getIndexStatus(
            {
                "knowledgeBaseId": knowledgeBaseId.strip(),
                "userId": context.request.context.principal_id,
            },
        )
