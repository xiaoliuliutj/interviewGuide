from typing import Protocol

from agent.Agents.models import (
    AgentContext,
    AgentMessage,
    SkillDefinition,
    ToolCall,
    ToolExecutionResult,
)
from agent.Common.results import AgentTaskType
from agent.Common.results import AgentOperationResponse


class SkillGateway(Protocol):
    """Provides task-scoped prompts and capability permissions from Skills."""

    async def resolveSkill(self, taskType: AgentTaskType) -> SkillDefinition:
        """Return the configured Skill for a Java-specified task type."""


class ToolGateway(Protocol):
    """Executes registered tools without exposing their implementations to AgentLoop."""

    async def executeTool(
        self,
        toolCall: ToolCall,
        context: AgentContext,
    ) -> ToolExecutionResult:
        """Execute one model-requested tool after implementation-side validation."""


class MemoryGateway(Protocol):
    """Loads session/user memory from the Memory module."""

    async def loadMemory(self, context: AgentContext) -> list[AgentMessage]:
        """Return memory entries relevant to the current run."""

    async def initializeSession(self, context: AgentContext) -> None:
        """创建面试会话的内部持久化状态。"""

    async def startTurn(self, context: AgentContext) -> str:
        """在开始面试回合前抢占会话执行权。"""

    async def finishTurn(self, context: AgentContext, assistantContent: str) -> int:
        """持久化完成回合并返回递增后的会话版本。"""

    async def abortTurn(self, context: AgentContext) -> None:
        """在失败时释放会话执行权。"""

    async def renewTurnLease(self, context: AgentContext) -> None:
        """在长时间 AgentLoop 中续期会话执行租约。"""

    async def saveRunResult(self, response: AgentOperationResponse) -> None:
        """持久化最终 run 响应，支持幂等重放。"""

    async def loadRunResult(self, runId: str, userId: str, sessionId: str) -> AgentOperationResponse | None:
        """读取同一 runId 的最终响应。"""


    async def deleteResumeMemory(self, userId: str, resumeId: str) -> None:
        """删除指定用户的简历长期记忆。"""

    async def deleteInterviewMemory(self, userId: str, sessionId: str) -> None:
        """删除指定用户指定会话的面试长期记忆。"""

    async def saveResumeEvaluation(self, userId: str, resumeId: str, evaluation: dict[str, object]) -> None:
        """保存简历分析完成后产生的长期记忆。"""

    async def saveInterviewCompletion(self, userId: str, sessionId: str, result: dict[str, object]) -> None:
        """保存已结束面试的长期记忆并更新用户面试总览。"""

    async def saveUserProfile(self, userId: str, profile: dict[str, object]) -> None:
        """保存用户画像的当前版本。"""


class RagGateway(Protocol):
    """Retrieves task-relevant documents from the RAG module."""

    async def retrieveKnowledge(self, context: AgentContext) -> list[str]:
        """Return retrieved knowledge snippets relevant to the current run."""

    # 旧同步索引入口已移除，索引统一通过 stageIndexDocument 异步处理。
        """解析并索引一个 Java 上传的文档。"""

    async def stageIndexDocument(self, payload: dict[str, object]) -> dict[str, object]:
        """持久化上传文件和异步索引任务。"""

    async def getIndexStatus(self, payload: dict[str, object]) -> dict[str, object]:
        """查询异步索引任务的当前状态。"""

    async def deleteKnowledgeBase(self, knowledgeBaseId: str, userId: str) -> None:
        """幂等删除知识库正文和检索数据。"""

    async def downloadDocument(self, payload: dict[str, object]) -> dict[str, object]:
        """返回指定用户知识库文档的原始内容和文件元数据。"""

    async def clearSessionCache(self, sessionId: str) -> None:
        """在面试结束时清理该会话的所有临时 RAG 缓存。"""

    async def deleteSessionSources(self, sessionId: str) -> None:
        """删除面试记录时同步删除该会话持久化的 RAG 来源追踪。"""
