from agent.Agents.agent_loop import AgentLoop
from agent.LLM.llm_service import LlmService
from agent.Agents.response_validator import ResponseValidator
from agent.Memory.memory_service import MemoryService
from agent.Memory.memory_event_worker import MemoryEventWorker
from agent.Common.Configs.settings import AgentSettings
from agent.Common.RabbitMQ.rabbitmq_service import RabbitMqService
from agent.RAG.rag_service import RagService
from agent.Skills.skill_service import SkillService
from agent.Tools.tool_service import ToolService
from agent.api.service import AgentApplicationService
from agent.Common.Postgres.postgres_service import PostgresService
from agent.Workflows.interview_repository import InterviewWorkflowRepository
from agent.Workflows.interview_workflow import InterviewWorkflow
from agent.Workflows.resume_repository import ResumeWorkflowRepository
from agent.Workflows.resume_workflow import ResumeWorkflow
from agent.Workflows.workflow_runtime import WorkflowRuntime


def createApplicationService() -> AgentApplicationService:
    """Compose concrete module services into the AgentLoop while keeping their implementations outside Agents."""
    llmService = LlmService(AgentSettings.from_environment())
    memoryService = MemoryService(llmService)
    ragService = RagService(llmService)
    agentLoop = AgentLoop(
        llmClient=llmService,
        skillGateway=SkillService(),
        toolGateway=ToolService(memoryService, ragService),
        memoryGateway=memoryService,
        ragGateway=ragService,
        responseValidator=ResponseValidator(),
    )
    settings = AgentSettings.from_environment()
    interviewRepository = InterviewWorkflowRepository(PostgresService(settings))
    resumeRepository = ResumeWorkflowRepository(PostgresService(settings))
    workflowRuntime = WorkflowRuntime(
        llmService,
        agentLoop,
        InterviewWorkflow(llmService, memoryService, ragService, interviewRepository),
        ResumeWorkflow(llmService, memoryService, resumeRepository),
        interviewRepository,
        resumeRepository,
    )
    return AgentApplicationService(agentLoop, workflowRuntime)


def createMemoryEventWorker() -> tuple[MemoryEventWorker, RabbitMqService]:
    """创建摘要补偿消费者及其 RabbitMQ 连接服务，供 FastAPI 生命周期注册。"""
    memoryService = MemoryService()
    rabbitMqService = RabbitMqService(AgentSettings.from_environment())
    return MemoryEventWorker(memoryService), rabbitMqService
