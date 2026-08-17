import asyncio
import logging

from fastapi import FastAPI, Request

from agent.Api.CapabilityApi import registerCapabilityApi
from agent.Api.Service import AgentApplicationService, createApplicationService, createMemoryEventWorker
from agent.Common.AgentRequest import AgentHealthResponse, AgentOperationRequest
from agent.Common.AgentResults import AgentError, AgentOperationResponse
from agent.Common.Exceptions.AgentException import AgentException, AgentRequestContractError
from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Postgres.PostgresService import PostgresService
from agent.Memory.memoryOutboxPublisher import MemoryOutboxPublisher
from agent.Memory.memoryRepository import MemoryRepository

logger = logging.getLogger(__name__)

ERROR_MESSAGES = {
    400: "Agent 服务暂时不可用", 401: "Agent 服务请求超时", 402: "Agent 执行失败",
    403: "不支持当前 Agent 任务", 404: "Agent 请求格式不符合协议",
    410: "大模型服务暂时不可用", 411: "大模型服务认证失败", 412: "大模型请求过于频繁",
    413: "大模型请求超。", 414: "大模型未返回有效内容", 415: "大模型工具调用格式错误",
    416: "大模型输出格式不符合要求", 417: "大模型拒绝处理当前内容", 418: "大模型上下文超过限制",
    420: "请求的工具未注册", 421: "当前任务无权使用该工具", 422: "工具调用参数不合法", 423: "工具执行超时", 424: "工具执行失败",
    430: "记忆服务暂时不可用", 431: "读取记忆失败", 432: "写入记忆失败",
    440: "知识库服务暂时不可用", 441: "知识库检索失败", 442: "向量生成失败", 443: "向量库操作失败", 444: "知识库索引失败", 445: "知识库删除失败", 446: "文档解析失败", 447: "文档超过允许大小",
    450: "Redis 服务暂时不可用", 452: "RabbitMQ 服务暂时不可用",
    460: "Agent 会话不存在", 461: "当前会话正在处理其他请求", 462: "当前会话状态不允许该操作", 463: "Agent 状态保存失败", 465: "Agent 执行轮数超过限制", 466: "Agent 执行超过截止时间",
    470: "Agent 配置不正确", 471: "Agent 提示词不存在", 472: "Agent Skill 不存在", 473: "Agent Skill 配置不正确", 474: "网页访问失败", 475: "网页内容不安全", 476: "简历文档解析失败", 477: "简历分析失败", 478: "简历分析结果不存在", 499: "Agent 内部错误",
}


def createFailureResponse(request: AgentOperationRequest, error: AgentException) -> AgentOperationResponse:
    """将 Agent 异常转换为 Java 可稳定解析的失败响应。"""
    return AgentOperationResponse(api_version=request.context.api_version, request_id=request.context.request_id,
        run_id=request.context.run_id, principal_id=request.context.principal_id,
        conversation_id=request.context.conversation_id, status_code=error.status_code, status="FAILED",
        state_version=request.state_version, data=None,
        error=AgentError(type=type(error).__name__, message=ERROR_MESSAGES.get(int(error.status_code), "Agent 执行失败"), retryable=error.retryable))


def createApp(service: AgentApplicationService | None = None) -> FastAPI:
    """创建 LLM 对话接口，并启动索引、工作流和记忆后台任务。"""
    app = FastAPI(title="Interview Agent Internal API", version="v1")
    app.state.agentService = service or createApplicationService()
    registerCapabilityApi(app)

    @app.on_event("startup")
    async def startBackgroundTasks() -> None:
        """初始化消息消费者，并持续执行可恢复的后台任务。"""
        worker, rabbitMqService = createMemoryEventWorker()
        app.state.memoryEventWorker, app.state.memoryRabbitMqService = worker, rabbitMqService
        await rabbitMqService.consumeEvents(worker.handleEvent)
        repository = MemoryRepository(PostgresService(AgentSettings.from_environment()))
        app.state.memoryPublisherRepository = repository
        await repository.postgresService.runMemoryMigrations()
        await repository.postgresService.runRagMigrations()
        publisher = MemoryOutboxPublisher(repository, rabbitMqService)
        async def executeBackgroundJobs() -> None:
            while True:
                try:
                    runtime = app.state.agentService.workflowRuntime
                    await app.state.agentService.agentLoop.ragService.processIndexJobs()
                    if runtime is not None:
                        await runtime.processResumeJobs()
                        await runtime.processExpiredInterviews()
                    await publisher.publishPendingEvents()
                except Exception:
                    logger.exception("Agent 后台任务执行失败，将在下一轮继续")
                await asyncio.sleep(2)
        app.state.backgroundTask = asyncio.create_task(executeBackgroundJobs())

    @app.on_event("shutdown")
    async def stopBackgroundTasks() -> None:
        """停止后台任务并释放消息、数据库和 Agent 服务资源。"""
        task = getattr(app.state, "backgroundTask", None)
        if task is not None: task.cancel()
        serviceInstance = getattr(app.state, "memoryRabbitMqService", None)
        if serviceInstance is not None: await serviceInstance.close()
        worker = getattr(app.state, "memoryEventWorker", None)
        if worker is not None: await worker.close()
        repository = getattr(app.state, "memoryPublisherRepository", None)
        if repository is not None: await repository.postgresService.close()
        await app.state.agentService.close()

    @app.get("/internal/v1/health", response_model=AgentHealthResponse)
    async def health() -> AgentHealthResponse:
        return AgentHealthResponse(status="UP")

    @app.post("/internal/v1/runs", response_model=AgentOperationResponse)
    async def runAgent(payload: AgentOperationRequest, request: Request) -> AgentOperationResponse:
        """执行对话型 LLM 请求，并将受控异常转换为统一响应。"""
        try:
            if payload.mode != "conversation":
                raise AgentRequestContractError("runs 接口仅接收 conversation 请求")
            return await request.app.state.agentService.dispatch(payload)
        except AgentException as error:
            return createFailureResponse(payload, error)
    return app


app = createApp()
