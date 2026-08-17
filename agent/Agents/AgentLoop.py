import asyncio
import json
from contextlib import suppress

from agent.LLM.llmService import LlmService
from agent.Common.PromptService import PromptLoader
from agent.Common.AgentModels import (
    AgentContext,
    AgentLoopCommand,
    AgentMessage,
    ToolCall,
    ToolExecutionResult,
)
from agent.Agents.AgentResponse import ResponseValidator
from agent.Memory.memoryService import MemoryService
from agent.RAG.ragService import RagService
from agent.Skills.skillsService import SkillService
from agent.Tools.toolsService import ToolService
from agent.Common.Exceptions.AgentException import (
    AgentException,
    AgentInternalError,
    AgentRunStepLimitError,
    LlmOutputSchemaError,
    ToolNotAuthorizedError,
)
from agent.Common.AgentResults import (
    AgentError,
    AgentOperationResponse,
    AgentResultStatus,
    AgentTaskType,
)


class AgentLoop:
    """运行受限 ReAct 主循环，并直接协。"Memory、RAG、Skills 。"Tools 服务。"""

    def __init__(
        self,
        llmClient: LlmService,
        skillsService: SkillService,
        toolsService: ToolService,
        memoryService: MemoryService,
        ragService: RagService,
        responseValidator: ResponseValidator,
        promptLoader: PromptLoader | None = None,
        maxSteps: int = 4,
    ) -> None:
        """注入领域服务并设。"AgentLoop 的最大推理轮数。"""
        self.llmClient = llmClient
        self.skillsService = skillsService
        self.toolsService = toolsService
        self.memoryService = memoryService
        self.ragService = ragService
        self.responseValidator = responseValidator
        self.promptLoader = promptLoader or PromptLoader()
        self.maxSteps = maxSteps

    async def run(self, command: AgentLoopCommand) -> AgentOperationResponse:
        """Build task context, run at most maxSteps ReAct turns, and return a verified response."""
        context: AgentContext | None = None
        leaseTask: asyncio.Task | None = None
        try:
            isConversation = command.request.task_type in {
                AgentTaskType.CONVERSATION,
                AgentTaskType.INTERVIEW_TURN,
            }
            if isConversation:
                replay = await self.memoryService.loadRunResult(
                    command.request.context.run_id,
                    command.request.context.principal_id,
                    command.request.context.conversation_id,
                )
                if replay is not None:
                    return replay
            skill = await self.skillsService.resolveSkill(command.request.task_type)
            context = AgentContext(request=command.request, skill=skill)
            if command.request.task_type == AgentTaskType.RESUME_MEMORY_DELETION:
                await self.memoryService.deleteResumeMemory(
                    command.request.context.principal_id,
                    str(command.parsedPayload["resumeId"]),
                )
                return self.createNoDataResponse(context)
            if command.request.task_type == AgentTaskType.INTERVIEW_MEMORY_DELETION:
                await self.ragService.clearSessionCache(command.request.context.conversation_id)
                await self.ragService.deleteSessionSources(command.request.context.conversation_id)
                await self.memoryService.deleteInterviewMemory(
                    command.request.context.principal_id,
                    command.request.context.conversation_id,
                )
                return self.createNoDataResponse(context)
            context.messages.append(AgentMessage(role="system", content=skill.systemPrompt))
            context.messages.append(
                AgentMessage(
                    role="system",
                    content=self.promptLoader.loadPrompt("Agent/agentResponseProtocol.txt"),
                )
            )

            if command.request.task_type == AgentTaskType.INTERVIEW_SESSION_INITIALIZATION or isConversation:
                await self.memoryService.initializeSession(context)
                candidate = command.parsedPayload.get("candidate")
                if isinstance(candidate, dict):
                    await self.memoryService.saveUserProfile(
                        command.request.context.principal_id,
                        candidate,
                    )

            if isConversation:
                turnStatus = await self.memoryService.startTurn(context)
                if turnStatus == "EXISTING_PROCESSING":
                    return self.createProcessingResponse(context)
                if turnStatus in {"EXISTING_COMPLETED", "EXISTING_FAILED"}:
                    replay = await self.memoryService.loadRunResult(
                        command.request.context.run_id,
                        command.request.context.principal_id,
                        command.request.context.conversation_id,
                    )
                    if replay is not None:
                        return replay
                    return self.createProcessingResponse(context)
                leaseTask = asyncio.create_task(self.keepTurnLease(context))

            await self.enrichContext(context)
            context.messages.append(
                AgentMessage(
                    role="user",
                    content=json.dumps(command.parsedPayload, ensure_ascii=False),
                )
            )

            for step in range(1, self.maxSteps + 1):
                context.stepCount = step
                if isConversation:
                    await self.memoryService.renewTurnLease(context)
                modelResponse = await self.llmClient.generateAgentResponse(context)
                try:
                    self.responseValidator.validateModelResponse(modelResponse)
                except LlmOutputSchemaError as error:
                    # An invalid model decision is fed back as context so the next turn can repair it.
                    context.messages.append(
                        AgentMessage(role="tool", content=f"FORMAT_ERROR: {error}")
                    )
                    continue

                if modelResponse.finalData is not None:
                    response = self.createSuccessResponse(context, modelResponse.finalData)
                    if command.request.task_type in {
                        AgentTaskType.RESUME_ANALYSIS,
                        AgentTaskType.RESUME_MEMORY_ACTIVATION,
                    }:
                        await self.memoryService.saveResumeEvaluation(
                            command.request.context.principal_id,
                            str(command.parsedPayload["resumeId"]),
                            modelResponse.finalData,
                        )
                    if (
                        command.request.task_type == AgentTaskType.INTERVIEW_ACTION
                        and str(command.parsedPayload.get("action", "")).upper()
                        in {"END", "FINISH", "COMPLETE"}
                    ):
                        await self.ragService.clearSessionCache(command.request.context.conversation_id)
                        await self.memoryService.saveInterviewCompletion(
                            command.request.context.principal_id,
                            command.request.context.conversation_id,
                            modelResponse.finalData,
                        )
                    self.responseValidator.validateFinalResponse(command.request, response)
                    if isConversation:
                        response = response.model_copy(
                            update={
                                "state_version": await self.memoryService.finishTurn(
                                    context,
                                    str(modelResponse.finalData),
                                ),
                            }
                        )
                    if isConversation:
                        await self.memoryService.saveRunResult(response)
                    return response

                await self.executeRequestedTool(context, modelResponse.toolCall)

            raise AgentRunStepLimitError(
                f"Agent did not finish within {self.maxSteps} ReAct steps",
            )
        except AgentException as error:
            if context is not None and isConversation:
                await self.cleanupFailedTurn(context)
            response = self.createFailureResponse(command, error)
            if context is not None and isConversation:
                await self.persistFailureResult(response)
            return response
        except Exception:
            if context is not None and isConversation:
                await self.cleanupFailedTurn(context)
            return self.createFailureResponse(
                command,
                AgentInternalError("Unexpected error while executing AgentLoop"),
            )
        finally:
            if leaseTask is not None:
                leaseTask.cancel()
                with suppress(asyncio.CancelledError):
                    await leaseTask

    async def keepTurnLease(self, context: AgentContext) -> None:
        """在模型一次调用超过锁 TTL 时持续续租，避免相同会话错误并发进入。"
        主循环仍会在每次模型调用前续租；后台任务仅覆盖单次长调用期间的空档。"        """
        while True:
            await asyncio.sleep(30)
            await self.memoryService.renewTurnLease(context)

    async def cleanupFailedTurn(self, context: AgentContext) -> None:
        """尽力释放失败回合的租约；清理异常不能覆盖原始业务错误。"""
        try:
            await self.memoryService.abortTurn(context)
        except Exception:
            return

    async def persistFailureResult(self, response: AgentOperationResponse) -> None:
        """尽力保存失败结果供幂等重试重放，持久化故障不再次抛出。"""
        try:
            await self.memoryService.saveRunResult(response)
        except Exception:
            return

    async def enrichContext(self, context: AgentContext) -> None:
        """Load optional Memory and RAG context; failures become messages and never terminate the run."""
        if context.skill.memoryEnabled:
            try:
                memoryItems = await self.memoryService.loadMemory(context)
                context.messages.extend(memoryItems)
            except Exception as error:
                # Optional memory cannot make the primary task fail; expose the fault to the model instead.
                context.messages.append(
                    AgentMessage(role="tool", content=f"MEMORY_UNAVAILABLE: {error}")
                )

        if context.skill.ragEnabled:
            try:
                knowledgeItems = await self.ragService.retrieveKnowledge(context)
                context.messages.extend(
                    AgentMessage(role="tool", content=item, name="rag")
                    for item in knowledgeItems
                )
            except Exception as error:
                # RAG is supporting context, so a retrieval outage remains recoverable within this run.
                context.messages.append(
                    AgentMessage(role="tool", content=f"RAG_UNAVAILABLE: {error}")
                )

    async def executeRequestedTool(
        self,
        context: AgentContext,
        toolCall: ToolCall | None,
    ) -> None:
        """Authorize and execute one tool; tool failures are returned to the model as recoverable context."""
        if toolCall is None:
            raise LlmOutputSchemaError("Validated model response has no tool call")
        if toolCall.name not in context.skill.allowedToolNames:
            result = ToolExecutionResult(
                name=toolCall.name,
                content=str(ToolNotAuthorizedError(f"Tool {toolCall.name} is not allowed")),
                succeeded=False,
            )
        else:
            try:
                result = await self.toolsService.executeTool(toolCall, context)
            except Exception as error:
                # A Tool failure becomes a tool message so the model can choose a fallback action.
                result = ToolExecutionResult(
                    name=toolCall.name,
                    content=f"TOOL_ERROR: {error}",
                    succeeded=False,
                )

        context.messages.append(
            AgentMessage(role="tool", content=result.content, name=result.name)
        )

    def createSuccessResponse(
        self,
        context: AgentContext,
        data: dict[str, object],
    ) -> AgentOperationResponse:
        """Create a standard successful Common response after the model has selected final data."""
        request = context.request
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=AgentResultStatus.SUCCESS_WITH_DATA,
            status="COMPLETED",
            state_version=request.state_version,
            data=data,
            error=None,
        )

    def createFailureResponse(
        self,
        command: AgentLoopCommand,
        error: AgentException,
    ) -> AgentOperationResponse:
        """Convert a controlled Agent exception into the protocol result returned to Java."""
        request = command.request
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
                message=str(error),
                retryable=error.retryable,
            ),
        )

    def createProcessingResponse(self, context: AgentContext) -> AgentOperationResponse:
        """返回幂等重试期间的处理中状态，阻止相同 runId 重复调用模型。"""
        request = context.request
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=AgentResultStatus.SUCCESS_WITHOUT_DATA,
            status="PROCESSING",
            state_version=request.state_version,
            data=None,
            error=None,
        )

    def createNoDataResponse(self, context: AgentContext) -> AgentOperationResponse:
        """创建不携带结果体的成功响应，用于已完成的 Agent 内部清理任务。"""
        request = context.request
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=AgentResultStatus.SUCCESS_WITHOUT_DATA,
            status="COMPLETED",
            state_version=request.state_version,
            data=None,
            error=None,
        )
