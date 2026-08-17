from typing import Any

from agent.Agents.AgentLoop import AgentLoop
import json

from agent.Common.AgentModels import AgentContext, AgentLoopCommand, ToolCall
from agent.Common.Exceptions.AgentException import AgentRequestContractError
from agent.Common.AgentResults import AgentOperationResponse, AgentTaskType
from agent.Common.AgentRequest import AgentOperationRequest
from agent.WorkFlows.workflowService import WorkflowService
from agent.Agents.AgentResponse import ResponseValidator
from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Postgres.PostgresService import PostgresService
from agent.Common.RabbitMQ.RabbitMqService import RabbitMqService
from agent.LLM.llmService import LlmService
from agent.Memory.memoryEventWorker import MemoryEventWorker
from agent.Memory.memoryService import MemoryService
from agent.RAG.ragService import RagService
from agent.Skills.skillsService import SkillService
from agent.Tools.toolsService import ToolService
from agent.WorkFlows.Interview.interviewRepository import InterviewWorkflowRepository
from agent.WorkFlows.Interview.interviewWorkflow import InterviewWorkflow
from agent.WorkFlows.Resume.resumeRepository import ResumeWorkflowRepository
from agent.WorkFlows.Resume.resumeWorkflow import ResumeWorkflow


class AgentApplicationService:
    """Agent 的通用入口，负责协议校验和能力路由，不理解调用方业务对象。"""

    def __init__(
        self,
        agentLoop: AgentLoop,
        workflowRuntime: WorkflowService | None = None,
    ) -> None:
        """保存已经组装好的 Agent 运行时，避免 API 层创建领域服务。"""
        self.agentLoop = agentLoop
        self.workflowRuntime = workflowRuntime

    async def close(self) -> None:
        """关闭 Agent 内部持有的可释放资源。"""
        if self.workflowRuntime is not None:
            await self.workflowRuntime.close()
        memoryService = getattr(self.agentLoop, "memoryService", None)
        if memoryService is not None and hasattr(memoryService, "close"):
            await memoryService.close()
        ragService = getattr(self.agentLoop, "ragService", None)
        if ragService is not None and hasattr(ragService, "close"):
            await ragService.close()

    async def dispatch(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """校验通用请求并路由到对话 AgentLoop 或确定性能力。"""
        parsedPayload = self.parsePayload(request)
        if request.mode == "capability":
            if self.workflowRuntime is not None and request.capability in {
                "resume.upload", "resume.status", "resume.reanalyze", "resume.download", "resume.delete"
            }:
                return await self.workflowRuntime.handleResumeCapability(request)
            if self.workflowRuntime is not None and request.capability in {
                "interview.complete", "interview.close", "interview.pause"
            }:
                return await self.workflowRuntime.handleInterviewCapability(request)
            return await self.dispatchCapability(request, parsedPayload)
        if self.workflowRuntime is not None:
            return await self.workflowRuntime.handleConversation(request)
        command = AgentLoopCommand(request=request, parsedPayload=parsedPayload)
        return await self.agentLoop.run(command)

    async def dispatchCapability(
        self,
        request: AgentOperationRequest,
        parsedPayload: dict[str, Any],
    ) -> AgentOperationResponse:
        """执行 RAG 文件管理等确定性能力，避免。"LLM 决定基础设施操作。"""
        ragService = self.agentLoop.ragService
        taskType = request.task_type
        if taskType == AgentTaskType.RAG_DOCUMENT_INDEXING:
            data = await ragService.stageIndexDocument(parsedPayload)
            return self.createResponse(request, 100, "PROCESSING", data)
        if taskType == AgentTaskType.RAG_DOCUMENT_DELETION:
            await ragService.deleteKnowledgeBase(
                str(parsedPayload["knowledgeBaseId"]),
                request.context.principal_id,
            )
            return self.createResponse(request, 101, "COMPLETED", None)
        if taskType == AgentTaskType.RAG_DOCUMENT_DOWNLOAD:
            data = await ragService.downloadDocument(parsedPayload)
            return self.createResponse(request, 100, "COMPLETED", data)
        if taskType == AgentTaskType.RAG_DOCUMENT_INDEX_STATUS:
            data = await ragService.getIndexStatus(parsedPayload)
            return self.createResponse(request, 100, "COMPLETED", data)
        if taskType == AgentTaskType.URL_KNOWLEDGE_BASE_CRAWL:
            data = await ragService.crawlUrlKnowledgeBase(parsedPayload)
            return self.createResponse(request, 100, "COMPLETED", data)
        if taskType == AgentTaskType.URL_KNOWLEDGE_BASE_IMPORT:
            data = await ragService.importUrlKnowledgeBase(parsedPayload)
            return self.createResponse(request, 100, "PROCESSING", data)
        if taskType == AgentTaskType.URL_KNOWLEDGE_BASE_ARCHIVE:
            data = await ragService.downloadUrlCrawlArchive(parsedPayload)
            return self.createResponse(request, 100, "COMPLETED", data)
        if taskType in {AgentTaskType.WEB_PAGE_FETCH, AgentTaskType.WEBSITE_CRAWL}:
            toolName = "fetchWebPage" if taskType == AgentTaskType.WEB_PAGE_FETCH else "crawlWebPages"
            skill = await self.agentLoop.skillsService.resolveSkill(taskType)
            context = AgentContext(request=request, skill=skill)
            result = await self.agentLoop.toolsService.executeTool(
                ToolCall(name=toolName, arguments=parsedPayload),
                context,
            )
            return self.createResponse(request, 100, "COMPLETED", json.loads(result.content))
        raise AgentRequestContractError("Agent capability 未实。")

    def parsePayload(self, request: AgentOperationRequest) -> dict[str, Any]:
        """把通用 data 与调用上下文合并为内部服务需要的 payload。"""
        payload = dict(request.payload)
        payload["userId"] = request.context.principal_id
        payload["runId"] = request.context.run_id
        if request.mode == "conversation":
            if not request.prompt.strip():
                raise AgentRequestContractError("conversation 请求必须提供 prompt")
            return payload

        requiredFields = {
            AgentTaskType.RAG_DOCUMENT_INDEXING: (
                "knowledgeBaseId",
                "documentId",
                "documentContent",
            ),
            AgentTaskType.RAG_DOCUMENT_DELETION: ("knowledgeBaseId",),
            AgentTaskType.RAG_DOCUMENT_DOWNLOAD: (
                "knowledgeBaseId",
                "documentId",
            ),
            AgentTaskType.RAG_DOCUMENT_INDEX_STATUS: ("knowledgeBaseId",),
            AgentTaskType.URL_KNOWLEDGE_BASE_CRAWL: ("url",),
            AgentTaskType.URL_KNOWLEDGE_BASE_IMPORT: ("previewToken",),
            AgentTaskType.URL_KNOWLEDGE_BASE_ARCHIVE: ("previewToken",),
            AgentTaskType.WEB_PAGE_FETCH: ("url",),
            AgentTaskType.WEBSITE_CRAWL: ("url",),
        }
        for field in requiredFields.get(request.task_type, ()):
            value = payload.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise AgentRequestContractError(
                    f"data.{field} is required for capability {request.capability}",
                )
        return payload

    def createResponse(
        self,
        request: AgentOperationRequest,
        statusCode: int,
        status: str,
        data: dict[str, Any] | None,
    ) -> AgentOperationResponse:
        """创建通用能力响应，确保调用关联信息原样返回。"""
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=statusCode,
            status=status,
            state_version=request.state_version,
            data=data,
        )


def createApplicationService() -> AgentApplicationService:
    """组装 AgentLoop、领域服务和工作流服务，。"HTTP 接口统一调用。"""
    settings = AgentSettings.from_environment()
    llmService = LlmService(settings)
    memoryService = MemoryService(llmService)
    ragService = RagService(llmService)
    agentLoop = AgentLoop(
        llmClient=llmService,
        skillsService=SkillService(),
        toolsService=ToolService(),
        memoryService=memoryService,
        ragService=ragService,
        responseValidator=ResponseValidator(),
    )
    interviewRepository = InterviewWorkflowRepository(PostgresService(settings))
    resumeRepository = ResumeWorkflowRepository(PostgresService(settings))
    workflowService = WorkflowService(
        llmService,
        agentLoop,
        InterviewWorkflow(llmService, memoryService, ragService, interviewRepository),
        ResumeWorkflow(llmService, memoryService, resumeRepository),
        interviewRepository,
        resumeRepository,
    )
    return AgentApplicationService(agentLoop, workflowService)


def createMemoryEventWorker() -> tuple[MemoryEventWorker, RabbitMqService]:
    """创建记忆摘要事件消费者与。"RabbitMQ 服务实例。"""
    return MemoryEventWorker(MemoryService()), RabbitMqService(AgentSettings.from_environment())
