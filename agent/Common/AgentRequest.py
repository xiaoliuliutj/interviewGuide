from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.Common.AgentResults import AgentTaskType


class AgentRequestContext(BaseModel):
    """定义所。"Agent 请求共用的调用关联信息。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    api_version: str = Field(alias="apiVersion", min_length=1)
    request_id: str = Field(alias="requestId", min_length=1)
    run_id: str = Field(alias="runId", min_length=1)
    principal_id: str = Field(alias="principalId", min_length=1)
    conversation_id: str = Field(alias="conversationId", min_length=1)
    timestamp: datetime


class AgentOperationRequest(BaseModel):
    """定义 Java 或其他调用方提交。"Agent 的稳定请求格式。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    context: AgentRequestContext
    mode: Literal["conversation", "capability"] = "conversation"
    capability: str | None = None
    prompt: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    state_version: int = Field(default=0, alias="stateVersion", ge=0)
    task_type: AgentTaskType = Field(default=AgentTaskType.CONVERSATION, exclude=True)

    def model_post_init(self, __context: Any) -> None:
        """根据 capability 生成 Agent 内部路由标识，保持对外请求字段稳定。"""
        capabilityMap = {
            "knowledge_base.index": AgentTaskType.RAG_DOCUMENT_INDEXING,
            "knowledge_base.index_status": AgentTaskType.RAG_DOCUMENT_INDEX_STATUS,
            "knowledge_base.delete": AgentTaskType.RAG_DOCUMENT_DELETION,
            "knowledge_base.download": AgentTaskType.RAG_DOCUMENT_DOWNLOAD,
            "knowledge_base.url_crawl": AgentTaskType.URL_KNOWLEDGE_BASE_CRAWL,
            "knowledge_base.url_import": AgentTaskType.URL_KNOWLEDGE_BASE_IMPORT,
            "knowledge_base.url_archive": AgentTaskType.URL_KNOWLEDGE_BASE_ARCHIVE,
            "resume.upload": AgentTaskType.RESUME_DOCUMENT_UPLOAD,
            "resume.status": AgentTaskType.RESUME_ANALYSIS_STATUS,
            "resume.reanalyze": AgentTaskType.RESUME_REANALYZE,
            "resume.download": AgentTaskType.RESUME_DOCUMENT_DOWNLOAD,
            "resume.delete": AgentTaskType.RESUME_DOCUMENT_DELETION,
            "interview.complete": AgentTaskType.INTERVIEW_SESSION_COMPLETION,
            "interview.close": AgentTaskType.INTERVIEW_SESSION_CLOSE,
            "interview.pause": AgentTaskType.INTERVIEW_SESSION_PAUSE,
            "web.fetch": AgentTaskType.WEB_PAGE_FETCH,
            "web.crawl": AgentTaskType.WEBSITE_CRAWL,
        }
        if self.mode == "capability":
            resolved = capabilityMap.get(self.capability or "")
            if resolved is None:
                raise ValueError("未知 Agent capability")
            object.__setattr__(self, "task_type", resolved)

    @property
    def payload(self) -> dict[str, Any]:
        """提供包含 prompt 内容的统一数据视图给内部服务使用。"""
        payload = dict(self.data)
        if self.prompt:
            payload.setdefault("answer", self.prompt)
        return payload


class AgentHealthResponse(BaseModel):
    """定义 Agent 健康检查接口的响应格式。"""

    status: Literal["UP"]
