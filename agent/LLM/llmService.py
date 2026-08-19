import asyncio
import json
import logging
from typing import Any

from agent.Common.AgentModels import AgentContext, LlmResponse, ToolCall
from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Exceptions.AgentException import (
    AgentException,
    LlmAuthenticationError,
    LlmContextLimitExceededError,
    LlmOutputSchemaError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmTimeoutError,
)
from agent.Common.PromptService import PromptLoader


logger = logging.getLogger(__name__)


class LlmService:
    """为 Agent 内部模块提供统一的大模型调用、重试、异常映射和响应解析能力。"""

    def __init__(
        self,
        settings: AgentSettings | None = None,
        promptLoader: PromptLoader | None = None,
        timeoutSeconds: int = 60,
        retryCount: int = 2,
        retryDelaySeconds: float = 0.5,
    ) -> None:
        """保存调用策略与配置；OpenAI 客户端在首次请求时惰性创建。"""
        self.settings = settings or AgentSettings.from_environment()
        self.promptLoader = promptLoader or PromptLoader()
        self.timeoutSeconds = timeoutSeconds
        self.retryCount = retryCount
        self.retryDelaySeconds = retryDelaySeconds
        self.client: Any | None = None
        self.model: str | None = None
        self.embeddingClient: Any | None = None
        self.embeddingModel: str | None = None

    async def generateAgentResponse(self, context: AgentContext) -> LlmResponse:
        """把 Agent 上下文交给模型，并解析为最终数据或单次工具调用。"""
        messages = []
        for item in context.messages:
            role = "user" if item.role == "tool" else item.role
            content = (
                f"[TOOL_RESULT:{item.name or 'unknown'}] {item.content}"
                if item.role == "tool"
                else item.content
            )
            messages.append({"role": role, "content": content})
        payload = await self.requestJson(messages, temperature=0)
        toolPayload = payload.get("toolCall")
        if toolPayload is not None:
            if not isinstance(toolPayload, dict) or not isinstance(toolPayload.get("name"), str):
                raise LlmOutputSchemaError("toolCall 必须包含字符串 name")
            arguments = toolPayload.get("arguments", {})
            if not isinstance(arguments, dict):
                raise LlmOutputSchemaError("toolCall.arguments 必须是对象")
            return LlmResponse(toolCall=ToolCall(name=toolPayload["name"], arguments=arguments))
        finalData = payload.get("finalData", payload)
        if not isinstance(finalData, dict):
            raise LlmOutputSchemaError("finalData 必须是对象")
        return LlmResponse(finalData=finalData)

    async def summarizeConversation(self, previousSummary: str | None, messages: list[str]) -> str:
        """使用记忆目录下的摘要提示词压缩历史对话，保留下一轮面试所需事实。"""
        systemPrompt = self.promptLoader.loadPrompt("Memory/memorySessionSummarySystem.txt")
        userPrompt = self.promptLoader.loadPrompt(
            "Memory/session_summary_user.txt",
            previousSummary=previousSummary or "无",
            messages="\n".join(messages),
        )
        return await self.requestText(
            [
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": userPrompt},
            ],
            temperature=0,
        )

    async def requestJson(self, messages: list[dict[str, str]], temperature: float) -> dict[str, object]:
        """按参考项目方式校正结构化输出：清理代码块并有限次数反馈错误重试。"""
        workingMessages = list(messages)
        maxCorrections = 2
        lastError: Exception | None = None
        for correctionAttempt in range(maxCorrections + 1):
            content = await self.requestCompletion(workingMessages, temperature, jsonMode=True)
            try:
                payload = json.loads(self._stripJsonFence(content))
                if not isinstance(payload, dict):
                    raise TypeError("JSON 顶层必须是对象")
                return payload
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                lastError = error
                logger.warning(
                    "模型结构化输出校验失败，第 %s 次，原因=%s，原始内容=%s",
                    correctionAttempt + 1,
                    error,
                    content[:1000],
                )
                if correctionAttempt == maxCorrections:
                    break
                workingMessages.extend([
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "上一轮输出未通过 JSON 校验。请只修复格式并重新返回完整 JSON 对象，"
                            "不得输出 Markdown 代码块、解释文字、注释或额外字段。"
                            f"校验错误：{error}"
                        ),
                    },
                ])
        raise LlmOutputSchemaError("模型返回的内容不是合法 JSON") from lastError

    @staticmethod
    def _stripJsonFence(content: str) -> str:
        """兼容参考项目，移除模型包裹 JSON 的 Markdown 代码块标记。"""
        text = content.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            return "\n".join(lines[1:-1]).strip()
        return text

    async def requestText(self, messages: list[dict[str, str]], temperature: float) -> str:
        """请求普通文本响应，并拒绝空文本以防止空摘要或空结论被持久化。"""
        content = await self.requestCompletion(messages, temperature, jsonMode=False)
        if not content.strip():
            raise LlmOutputSchemaError("模型未返回有效文本")
        return content.strip()

    async def requestCompletion(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        jsonMode: bool,
    ) -> str:
        """按统一超时与重试策略调用 OpenAI Chat Completions，并返回原始文本。"""
        lastError: Exception | None = None
        for attempt in range(self.retryCount + 1):
            try:
                client, model = await self.getClient()
                response = await asyncio.wait_for(
                    model.ainvoke(messages),
                    timeout=self.timeoutSeconds,
                )
                content = self._messageContent(response)
                if not content:
                    raise LlmOutputSchemaError("模型返回空内容")
                return content
            except LlmOutputSchemaError:
                raise
            except TimeoutError as error:
                lastError = error
            except AgentException as error:
                if not error.retryable:
                    raise
                lastError = error
            except Exception as error:
                mappedError = self.mapProviderError(error)
                logger.exception("大模型请求失败，providerError=%s", error)
                if not mappedError.retryable:
                    raise mappedError
                lastError = mappedError
            if attempt < self.retryCount:
                await asyncio.sleep(self.retryDelaySeconds * (2**attempt))
        if isinstance(lastError, TimeoutError):
            raise LlmTimeoutError(f"大模型在 {self.retryCount + 1} 次尝试后仍超时") from lastError
        if isinstance(lastError, AgentException):
            raise lastError
        raise LlmProviderUnavailableError("大模型调用失败") from lastError

    async def getClient(self) -> tuple[Any, Any]:
        """使用与参考项目一致的 ChatOpenAI 创建 OpenAI-compatible 聊天模型。"""
        if self.client is None:
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as error:
                raise LlmProviderUnavailableError("缺少 langchain-openai SDK") from error
            baseUrl, model, apiKey = self.settings.requireOpenAiConfiguration()
            options: dict[str, object] = {
                "model": model,
                "api_key": apiKey,
                "temperature": self.settings.model_temperature,
                "timeout": self.settings.request_timeout_seconds,
                "max_retries": 0,
            }
            if baseUrl:
                options["base_url"] = baseUrl
            if self.settings.model_max_tokens is not None:
                options["max_tokens"] = self.settings.model_max_tokens
            self.client = ChatOpenAI(**options)
            self.model = model
        return self.client, self.client

    @staticmethod
    def _messageContent(response: Any) -> str | None:
        """兼容 ChatOpenAI AIMessage 的字符串和多段内容返回格式。"""
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments = []
            for item in content:
                if isinstance(item, str):
                    fragments.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    fragments.append(item["text"])
            return "".join(fragments) or None
        return None

    def mapProviderError(self, error: Exception) -> AgentException:
        """将供应商 HTTP 错误映射为对 Java 层稳定的 Agent 状态码。"""
        message = str(error).lower()
        statusCode = getattr(error, "status_code", None)
        if "timeout" in message or "timed out" in message:
            return LlmTimeoutError("OpenAI 请求超时")
        if statusCode in {401, 403}:
            return LlmAuthenticationError("OpenAI 鉴权失败")
        if statusCode == 429:
            return LlmRateLimitError("OpenAI 请求触发限流")
        if statusCode == 400 and ("context" in message or "token" in message):
            return LlmContextLimitExceededError("模型上下文超过限制")
        detail = str(error).strip()
        return LlmProviderUnavailableError(
            f"OpenAI 请求失败{(': ' + detail[:300]) if detail else ''}"
        )

    async def close(self) -> None:
        """关闭已创建的 OpenAI 客户端，供应用关闭生命周期释放连接。"""
        if self.client is not None:
            close = getattr(self.client, "aclose", None) or getattr(self.client, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            self.client = None
        if self.embeddingClient is not None:
            await self.embeddingClient.close()
            self.embeddingClient = None

    async def embedDocuments(self, texts: list[str]) -> list[list[float]]:
        """批量生成文档向量并校验返回数量与配置维度。"""
        if not texts:
            return []
        client, model, dimensions = await self.getEmbeddingClient()
        response = await self.requestEmbedding(client, model, texts, dimensions)
        vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts) or any(len(vector) != dimensions for vector in vectors):
            raise LlmOutputSchemaError("embedding 返回数量或向量维度不匹配")
        return vectors

    async def embedQuery(self, text: str) -> list[float]:
        """生成单条检索向量，复用与文档入库相同的 embedding 配置。"""
        vectors = await self.embedDocuments([text])
        return vectors[0]

    async def getEmbeddingClient(self) -> tuple[Any, str, int]:
        """惰性创建独立 embedding 客户端，并读取独立的 URL、模型和维度配置。"""
        baseUrl, model, apiKey, dimensions = self.settings.requireEmbeddingConfiguration()
        if self.embeddingClient is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as error:
                raise LlmProviderUnavailableError("缺少 openai SDK") from error
            self.embeddingClient = AsyncOpenAI(base_url=baseUrl, api_key=apiKey)
            self.embeddingModel = model
        return self.embeddingClient, self.embeddingModel, dimensions

    async def requestEmbedding(
        self,
        client: Any,
        model: str,
        texts: list[str],
        dimensions: int,
    ) -> Any:
        """按统一超时和重试策略调用 embedding 接口，并显式指定输出维度。"""
        lastError: Exception | None = None
        for attempt in range(self.retryCount + 1):
            try:
                return await asyncio.wait_for(
                    client.embeddings.create(
                        model=model,
                        input=texts,
                        dimensions=dimensions,
                    ),
                    timeout=self.timeoutSeconds,
                )
            except TimeoutError as error:
                lastError = error
            except Exception as error:
                mappedError = self.mapProviderError(error)
                if not mappedError.retryable:
                    raise mappedError
                lastError = mappedError
            if attempt < self.retryCount:
                await asyncio.sleep(self.retryDelaySeconds * (2**attempt))
        if isinstance(lastError, TimeoutError):
            raise LlmTimeoutError("embedding 请求超时") from lastError
        raise LlmProviderUnavailableError("embedding 请求失败") from lastError
