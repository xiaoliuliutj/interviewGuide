import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent.Api.CapabilityApi import registerCapabilityApi
from agent.Api.Service import AgentApplicationService, createApplicationService, createMemoryEventWorker
from agent.Common.AgentRequest import AgentHealthResponse, AgentOperationRequest
from agent.Common.AgentErrorCatalog import getAgentErrorMessage
from agent.Common.AgentErrorCatalog import getAgentErrorMessage
from agent.Common.AgentResults import AgentError, AgentOperationResponse
from agent.Common.Exceptions.AgentException import AgentException, AgentRequestContractError
from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Postgres.PostgresService import PostgresService
from agent.Memory.memoryOutboxPublisher import MemoryOutboxPublisher
from agent.Memory.memoryRepository import MemoryRepository

logger = logging.getLogger(__name__)

def createFailureResponse(request: AgentOperationRequest, error: AgentException) -> AgentOperationResponse:
    """将 Agent 异常转换为 Java 可稳定解析的失败响应。"""
    return AgentOperationResponse(api_version=request.context.api_version, request_id=request.context.request_id,
        run_id=request.context.run_id, principal_id=request.context.principal_id,
        conversation_id=request.context.conversation_id, status_code=error.status_code, status="FAILED",
        state_version=request.state_version, data=None,
        error=AgentError(type=type(error).__name__, message=getAgentErrorMessage(error.status_code), retryable=error.retryable))


def createApp(service: AgentApplicationService | None = None) -> FastAPI:
    """创建 LLM 对话接口，并启动索引、工作流和记忆后台任务。"""
    app = FastAPI(title="Interview Agent Internal API", version="v1")
    app.state.agentService = service or createApplicationService()
    registerCapabilityApi(app)

    @app.exception_handler(RequestValidationError)
    async def handleRequestValidation(request: Request, error: RequestValidationError) -> JSONResponse:
        """将 FastAPI 的 422 校验错误转换为统一 Agent 协议响应，避免 Java 丢失错误码。"""
        try:
            rawBody = await request.json()
        except Exception:
            rawBody = {}
        context = rawBody.get("context") if isinstance(rawBody, dict) else {}
        context = context if isinstance(context, dict) else {}
        response = {
            "apiVersion": context.get("apiVersion", "v1"),
            "requestId": context.get("requestId", "unknown"),
            "runId": context.get("runId", "unknown"),
            "principalId": context.get("principalId", "unknown"),
            "conversationId": context.get("conversationId", "unknown"),
            "statusCode": 404,
            "status": "FAILED",
            "stateVersion": rawBody.get("stateVersion", 0) if isinstance(rawBody, dict) else 0,
            "data": {"validation": jsonable_encoder(error.errors())},
            "error": {
                "type": "AgentRequestContractError",
                "message": getAgentErrorMessage(404),
                "retryable": False,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return JSONResponse(status_code=200, content=response)

    @app.on_event("startup")
    async def startBackgroundTasks() -> None:
        """初始化消息消费者，并持续执行可恢复的后台任务。"""
        worker, rabbitMqService = createMemoryEventWorker()
        app.state.memoryEventWorker, app.state.memoryRabbitMqService = worker, rabbitMqService

        # 重试连接 RabbitMQ，最多等待 30 秒
        max_retries = 10
        retry_delay = 3
        for attempt in range(max_retries):
            try:
                await rabbitMqService.consumeEvents(worker.handleEvent)
                logger.info("成功连接到 RabbitMQ")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"连接 RabbitMQ 失败 (尝试 {attempt + 1}/{max_retries}): {e}，{retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"连接 RabbitMQ 失败，已达到最大重试次数: {e}")
                    raise

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
