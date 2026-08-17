import asyncio
import logging

from fastapi import FastAPI, Request

from agent.Common.Exceptions.agent_exception import AgentException
from agent.Common.results import (
    AgentError,
    AgentOperationResponse,
)
from agent.api.contracts import (
    AgentHealthResponse,
    AgentOperationRequest,
)
from agent.api.dependencies import createApplicationService, createMemoryEventWorker
from agent.Memory.outbox_publisher import MemoryOutboxPublisher
from agent.Memory.memory_repository import MemoryRepository
from agent.Common.Postgres.postgres_service import PostgresService
from agent.Common.Configs.settings import AgentSettings
from agent.api.service import AgentApplicationService


logger = logging.getLogger(__name__)

ERROR_MESSAGES = {
    400: "Agent 服务暂时不可用",
    401: "Agent 服务请求超时",
    402: "Agent 执行失败",
    403: "不支持当前 Agent 任务",
    404: "Agent 请求格式不符合协议",
    410: "大模型服务暂时不可用",
    411: "大模型服务认证失败",
    412: "大模型请求过于频繁",
    413: "大模型请求超时",
    414: "大模型未返回有效内容",
    415: "大模型工具调用格式错误",
    416: "大模型输出格式不符合要求",
    417: "大模型拒绝处理当前内容",
    418: "大模型上下文超过限制",
    420: "请求的工具未注册",
    421: "当前任务无权使用该工具",
    422: "工具调用参数不合法",
    423: "工具执行超时",
    424: "工具执行失败",
    430: "记忆服务暂时不可用",
    431: "读取记忆失败",
    432: "写入记忆失败",
    440: "知识库服务暂时不可用",
    441: "知识库检索失败",
    442: "向量生成失败",
    443: "向量库操作失败",
    444: "知识库索引失败",
    445: "知识库删除失败",
    446: "文档解析失败",
    447: "文档超过允许大小",
    450: "Redis 服务暂时不可用",
    452: "RabbitMQ 服务暂时不可用",
    460: "Agent 会话不存在",
    461: "当前会话正在处理其他请求",
    462: "当前会话状态不允许该操作",
    463: "Agent 状态保存失败",
    465: "Agent 执行轮数超过限制",
    466: "Agent 执行超过截止时间",
    470: "Agent 配置不正确",
    471: "Agent 提示词不存在",
    472: "Agent Skill 不存在",
    473: "Agent Skill 配置不正确",
    474: "网页访问失败",
    475: "网页内容不安全",
    476: "简历文档解析失败",
    477: "简历分析失败",
    478: "简历分析结果不存在",
    499: "Agent 内部错误",
}


def createApp(service: AgentApplicationService | None = None) -> FastAPI:
    """Create the HTTP boundary used exclusively by the Java backend."""
    app = FastAPI(title="Interview Agent Internal API", version="v1")
    app.state.agentService = service or createApplicationService()

    @app.on_event("startup")
    async def startMemoryEventConsumer() -> None:
        """在 API 启动后注册摘要补偿消费者，避免 Outbox 事件无人处理。"""
        worker, rabbitMqService = createMemoryEventWorker()
        app.state.memoryEventWorker = worker
        app.state.memoryRabbitMqService = rabbitMqService
        await rabbitMqService.consumeEvents(worker.handleEvent)
        publisherRepository = MemoryRepository(PostgresService(AgentSettings.from_environment()))
        app.state.memoryPublisherRepository = publisherRepository
        await publisherRepository.postgresService.runMemoryMigrations()
        await publisherRepository.postgresService.runRagMigrations()
        ragService = app.state.agentService.agentLoop.ragGateway

        async def processRagIndexJobs() -> None:
            """持续处理已暂存的索引任务，进程重启后由数据库任务状态自动恢复。"""
            while True:
                try:
                    await ragService.processIndexJobs()
                except Exception:
                    pass
                await asyncio.sleep(2)

        app.state.ragIndexTask = asyncio.create_task(processRagIndexJobs())
        workflowRuntime = app.state.agentService.workflowRuntime

        async def processWorkflowJobs() -> None:
            """持续处理简历解析任务和超时面试，所有任务状态由各自工作流持久化恢复。"""
            while True:
                try:
                    if workflowRuntime is not None:
                        await workflowRuntime.processResumeJobs()
                        await workflowRuntime.processExpiredInterviews()
                except Exception:
                    logger.exception("工作流后台任务执行失败，将在下一轮重试")
                await asyncio.sleep(3)

        app.state.workflowTask = asyncio.create_task(processWorkflowJobs())
        publisher = MemoryOutboxPublisher(publisherRepository, rabbitMqService)

        async def publishOutboxEvents() -> None:
            """周期性扫描并发布 Outbox 事件，发布失败保留 PENDING 状态等待下次补偿。"""
            while True:
                try:
                    await publisher.publishPendingEvents()
                except Exception:
                    # 发布失败不改变 Outbox 的 PENDING 状态，下一轮扫描会继续补偿。
                    await asyncio.sleep(0)
                finally:
                    await asyncio.sleep(2)

        app.state.memoryOutboxTask = asyncio.create_task(publishOutboxEvents())

    @app.on_event("shutdown")
    async def stopMemoryEventConsumer() -> None:
        """在服务停止时关闭 RabbitMQ 连接，避免消费者连接泄漏。"""
        serviceInstance = getattr(app.state, "memoryRabbitMqService", None)
        task = getattr(app.state, "memoryOutboxTask", None)
        ragTask = getattr(app.state, "ragIndexTask", None)
        workflowTask = getattr(app.state, "workflowTask", None)
        if task is not None:
            task.cancel()
        if ragTask is not None:
            ragTask.cancel()
        if workflowTask is not None:
            workflowTask.cancel()
        if serviceInstance is not None:
            await serviceInstance.close()
        worker = getattr(app.state, "memoryEventWorker", None)
        if worker is not None:
            await worker.close()
        publisherRepository = getattr(app.state, "memoryPublisherRepository", None)
        if publisherRepository is not None:
            await publisherRepository.postgresService.close()
        await app.state.agentService.close()

    @app.get("/internal/v1/health", response_model=AgentHealthResponse)
    async def health() -> AgentHealthResponse:
        """Report whether the Agent HTTP process is available to Java."""
        return AgentHealthResponse(status="UP")

    @app.post(
        "/internal/v1/runs",
        response_model=AgentOperationResponse,
    )
    async def runAgent(
        payload: AgentOperationRequest,
        request: Request,
    ) -> AgentOperationResponse:
        """Run one task and convert controlled Agent exceptions into the Common response contract."""
        try:
            return await request.app.state.agentService.dispatch(payload)
        except AgentException as error:
            return createFailureResponse(payload, error)

    return app


def createFailureResponse(
    request: AgentOperationRequest,
    error: AgentException,
) -> AgentOperationResponse:
    """Build a correlation-safe failed response from an Agent exception."""
    return AgentOperationResponse(
        api_version=request.context.api_version,
        request_id=request.context.request_id,
        run_id=request.context.run_id,
        principal_id=request.context.principal_id,
        conversation_id=request.context.conversation_id,
        status_code=error.status_code,
        status="FAILED",
        state_version=request.state_version,
        data=None,
        error=AgentError(
            type=type(error).__name__,
            message=ERROR_MESSAGES.get(int(error.status_code), "Agent 执行失败"),
            retryable=error.retryable,
        ),
    )


app = createApp()
