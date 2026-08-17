from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.Common.results import AgentTaskType


class AgentRequestContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_version: str = Field(alias="apiVersion", min_length=1)
    request_id: str = Field(alias="requestId", min_length=1)
    run_id: str = Field(alias="runId", min_length=1)
    principal_id: str = Field(alias="principalId", min_length=1)
    conversation_id: str = Field(alias="conversationId", min_length=1)
    timestamp: datetime


class AgentOperationRequest(BaseModel):
    """调用方与 Agent 之间稳定的通用请求信封。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    context: AgentRequestContext
    mode: Literal["conversation", "capability"] = "conversation"
    capability: str | None = None
    prompt: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    state_version: int = Field(default=0, alias="stateVersion", ge=0)
    task_type: AgentTaskType = Field(
        default=AgentTaskType.CONVERSATION,
        exclude=True,
    )

    def model_post_init(self, __context: Any) -> None:
        """根据通用模式解析 Agent 内部能力，不把 Java 任务枚举暴露到协议中。"""
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
                raise ValueError("未知的 Agent capability")
            object.__setattr__(self, "task_type", resolved)

    @property
    def payload(self) -> dict[str, Any]:
        """将通用 data 转换为 Agent 内部现有模块使用的 payload 视图。"""
        payload = dict(self.data)
        if self.prompt:
            payload.setdefault("answer", self.prompt)
        return payload


class AgentHealthResponse(BaseModel):
    status: Literal["UP"]
