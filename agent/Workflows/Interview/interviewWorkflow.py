"""以六阶段状态机控制面试，并将语言判断限制在可验证的 LLM 节点内。"""

import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from agent.Common.AgentModels import AgentContext
from agent.Common.AgentModels import SkillDefinition
from agent.Common.Exceptions.AgentException import (
    AgentRequestContractError,
    AgentSessionStateError,
    LlmOutputSchemaError,
)
from agent.Common.AgentResults import AgentError, AgentOperationResponse, AgentResultStatus, AgentTaskType
from agent.LLM.llmService import LlmService
from agent.Memory.memoryService import MemoryService
from agent.Common.PromptService import PromptLoader
from agent.RAG.ragService import RagService
from agent.Common.AgentRequest import AgentOperationRequest
from agent.utils.security.data_masker import DataMasker
from agent.Workflows.Interview.interviewModels import (
    InterviewAction,
    InterviewEvaluation,
    InterviewIntent,
    InterviewIntentDecision,
    InterviewPlan,
    InterviewQuestion,
    InterviewRoute,
    InterviewSessionState,
    InterviewStage,
    InterviewStatus,
    InterviewSummary,
    InterviewTurn,
)
from agent.Workflows.Interview.interviewRepository import InterviewWorkflowRepository


class InterviewWorkflow:
    """执行面试初始化、回答处理、暂停恢复、结束总结和超时收敛的完整闭环。"""

    def __init__(
        self,
        llmService: LlmService,
        memoryService: MemoryService,
        ragService: RagService,
        repository: InterviewWorkflowRepository,
        promptLoader: PromptLoader | None = None,
        inactiveMinutes: int = 360,
    ) -> None:
        """装配面试业务需要的模型、记忆、检索和持久化依赖，禁止直接依赖 Java 业务对象。"""
        self.llmService = llmService
        self.memoryService = memoryService
        self.ragService = ragService
        self.repository = repository
        self.promptLoader = promptLoader or PromptLoader()
        self.dataMasker = DataMasker()
        self.inactiveMinutes = inactiveMinutes

    async def handleRequest(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """根据会话状态处理自然语言指令，已绑定面试会话时不再重新选择顶层工作流。"""
        replay = await self.repository.loadRunResult(
            request.context.run_id,
            request.context.conversation_id,
            request.context.principal_id,
        )
        if replay is not None:
            return AgentOperationResponse.model_validate(replay)
        state = await self.repository.loadState(
            request.context.conversation_id,
            request.context.principal_id,
        )
        if state is None:
            return await self.startInterview(request)
        if state.deadlineAt is not None and state.deadlineAt <= datetime.now(timezone.utc):
            return await self.closeInterview(request, state, "INACTIVITY_TIMEOUT")
        intent = await self.resolveIntent(request, state)
        if intent == InterviewIntent.QUERY_PROGRESS:
            return self.buildResponse(request, state, {
                "type": "INTERVIEW_PROGRESS",
                "progress": self.buildProgress(state),
                "content": state.currentQuestion,
            })
        if intent == InterviewIntent.PAUSE_INTERVIEW:
            return await self.pauseInterview(request, state)
        if intent == InterviewIntent.RESUME_INTERVIEW:
            return await self.resumeInterview(request, state)
        if intent == InterviewIntent.COMPLETE_INTERVIEW:
            return await self.completeInterview(request, state, False)
        return await self.handleAnswer(request, state)

    async def startInterview(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """创建会话、生成并校验一次性 InterviewPlan，再发出固定开场问题。"""
        payload = request.payload
        resumeIdValue = payload.get("resumeId")
        resumeId = resumeIdValue.strip() if isinstance(resumeIdValue, str) and resumeIdValue.strip() else None
        await self.repository.ensureSession(
            request.context.conversation_id,
            request.context.principal_id,
            resumeId,
        )
        claim = await self.repository.claimRun(
            request.context.conversation_id,
            request.context.principal_id,
            request.context.run_id,
            request.state_version,
        )
        if claim != "PROCESSING":
            replay = await self.repository.loadRunResult(
                request.context.run_id,
                request.context.conversation_id,
                request.context.principal_id,
            )
            if replay is not None:
                return AgentOperationResponse.model_validate(replay)
            raise AgentSessionStateError("会话初始化任务仍在执行")
        try:
            targetRoleValue = payload.get("targetRole")
            targetRole = (targetRoleValue.strip()
                          if isinstance(targetRoleValue, str) and targetRoleValue.strip()
                          else "通用技术岗位")
            difficulty = self.readDifficulty(payload.get("difficulty"))
            plan = await self.createPlan(request, targetRole, difficulty, resumeId)
            opening = self.promptLoader.loadPrompt("Interview/interviewOpening.txt", targetRole=targetRole)
            deadline = datetime.now(timezone.utc) + timedelta(minutes=self.inactiveMinutes)
            state = InterviewSessionState(
                sessionId=request.context.conversation_id,
                userId=request.context.principal_id,
                resumeId=resumeId,
                targetRole=targetRole,
                difficulty=difficulty,
                currentStage=InterviewStage.OPENING,
                currentTopic="自我介绍",
                currentQuestion=opening,
                plan=plan,
                stateVersion=request.state_version + 1,
                primaryQuestionCount=1,
                totalPrimaryQuestionCount=1,
                totalQuestionCount=1,
                stageQuestionCounts={InterviewStage.OPENING.value: 1},
                topicQuestionCounts={"自我介绍": 1},
                askedQuestionCatalog=[opening],
                deadlineAt=deadline,
            )
            response = self.buildResponse(request, state, {
                "type": "INTERVIEW_QUESTION",
                "content": opening,
                "progress": self.buildProgress(state),
            })
            await self.repository.commitState(
                state,
                request.context.run_id,
                request.state_version,
                response.model_dump_json(by_alias=True),
                assistantContent=self.dataMasker.maskText(opening),
            )
            return response
        except Exception as error:
            response = self.buildFailureResponse(request, error)
            await self.repository.failRun(
                request.context.conversation_id,
                request.context.run_id,
                response.model_dump_json(by_alias=True),
            )
            raise

    async def handleAnswer(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
    ) -> AgentOperationResponse:
        """严格执行评价、路由、检索、出题、原子提交的单轮面试顺序。"""
        if state.status != InterviewStatus.ACTIVE:
            raise AgentSessionStateError("当前面试会话不在可回答状态")
        if state.currentQuestion is None:
            raise AgentSessionStateError("当前面试缺少待回答问题")
        claim = await self.repository.claimRun(
            state.sessionId,
            state.userId,
            request.context.run_id,
            request.state_version,
        )
        if claim != "PROCESSING":
            replay = await self.repository.loadRunResult(request.context.run_id, state.sessionId, state.userId)
            if replay is not None:
                return AgentOperationResponse.model_validate(replay)
            raise AgentSessionStateError("当前回合正在处理中")
        try:
            answer = request.prompt.strip()
            evaluation = await self.evaluateAnswer(request, state, answer)
            if state.currentStage == InterviewStage.OPENING:
                state.plan = await self.createPlan(
                    request,
                    state.targetRole,
                    state.difficulty,
                    state.resumeId,
                    answer,
                )
            allowedActions = self.getAllowedActions(state, evaluation)
            route = await self.routeAnswer(request, state, evaluation, allowedActions)
            route = self.normalizeRoute(state, evaluation, route, allowedActions)
            turn = self.createTurn(state, request.context.run_id, answer, evaluation, route)
            state.turns.append(turn)
            state.lastActivityAt = datetime.now(timezone.utc)
            state.deadlineAt = state.lastActivityAt + timedelta(minutes=self.inactiveMinutes)
            if route.action == InterviewAction.END_INTERVIEW:
                return await self.finishAnsweredInterview(request, state, turn)
            self.applyRoute(state, route)
            evidence = await self.retrieveQuestionEvidence(request, state, route.nextTopic or "通用技术能力")
            question = await self.generateQuestion(state, route.nextTopic or "通用技术能力", evidence)
            self.registerQuestion(state, question, evidence, route)
            state.stateVersion = request.state_version + 1
            response = self.buildResponse(request, state, {
                "type": "INTERVIEW_TURN",
                "content": question,
                "evaluation": {
                    "summary": evaluation.evaluationSummary,
                    "score": evaluation.score,
                    "strengths": evaluation.strengths,
                    "weaknesses": evaluation.weaknesses,
                },
                "progress": self.buildProgress(state),
            })
            await self.repository.commitState(
                state,
                request.context.run_id,
                request.state_version,
                response.model_dump_json(by_alias=True),
                self.dataMasker.maskText(answer),
                self.dataMasker.maskText(question),
                turn,
            )
            return response
        except Exception as error:
            response = self.buildFailureResponse(request, error)
            await self.repository.failRun(state.sessionId, request.context.run_id, response.model_dump_json(by_alias=True))
            raise

    async def pauseInterview(self, request: AgentOperationRequest, state: InterviewSessionState) -> AgentOperationResponse:
        """将活动会话暂停并持久化，恢复时继续等待原问题而不重建上下文。"""
        if state.status in {InterviewStatus.COMPLETED, InterviewStatus.AUTO_TERMINATED}:
            raise AgentSessionStateError("已结束的面试不能暂停")
        return await self.persistControlTransition(request, state, InterviewStatus.PAUSED, "INTERVIEW_PAUSED")

    async def resumeInterview(self, request: AgentOperationRequest, state: InterviewSessionState) -> AgentOperationResponse:
        """恢复暂停会话，返回未回答的当前问题而不重复调用出题模型。"""
        if state.status != InterviewStatus.PAUSED:
            raise AgentSessionStateError("只有暂停中的面试可以恢复")
        return await self.persistControlTransition(request, state, InterviewStatus.ACTIVE, "INTERVIEW_RESUMED")

    async def completeInterview(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        autoTerminated: bool,
    ) -> AgentOperationResponse:
        """处理用户正常结束面试，统一生成最终报告并清理会话级 RAG 缓存。"""
        if state.status in {InterviewStatus.COMPLETED, InterviewStatus.AUTO_TERMINATED}:
            return self.buildResponse(request, state, {
                "type": "INTERVIEW_SUMMARY",
                "finalEvaluation": state.finalEvaluation.model_dump(mode="json") if state.finalEvaluation else None,
                "progress": self.buildProgress(state),
            })
        claim = await self.repository.claimRun(state.sessionId, state.userId, request.context.run_id, request.state_version)
        if claim != "PROCESSING":
            replay = await self.repository.loadRunResult(request.context.run_id, state.sessionId, state.userId)
            if replay is not None:
                return AgentOperationResponse.model_validate(replay)
            raise AgentSessionStateError("面试结束任务仍在执行")
        try:
            state.status = InterviewStatus.COMPLETING
            summary = await self.generateSummary(state)
            state.finalEvaluation = summary
            state.status = InterviewStatus.AUTO_TERMINATED if autoTerminated else InterviewStatus.COMPLETED
            state.currentStage = InterviewStage.SUMMARY
            state.currentQuestion = None
            state.currentTopic = None
            state.lastActivityAt = datetime.now(timezone.utc)
            state.stateVersion = request.state_version + 1
            response = self.buildResponse(request, state, {
                "type": "INTERVIEW_SUMMARY",
                "finalEvaluation": summary.model_dump(mode="json"),
                "progress": self.buildProgress(state),
            })
            await self.repository.commitState(
                state,
                request.context.run_id,
                request.state_version,
                response.model_dump_json(by_alias=True),
                assistantContent=self.dataMasker.maskText(summary.summary),
            )
            await self.persistCompletionMemory(state)
            await self.clearInterviewRagState(state.sessionId)
            return response
        except Exception as error:
            response = self.buildFailureResponse(request, error)
            await self.repository.failRun(state.sessionId, request.context.run_id, response.model_dump_json(by_alias=True))
            raise

    async def completeByCapability(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """处理前端明确提交面试的请求；正常结束必须生成并持久化最终评估。"""
        state = await self.repository.loadState(
            request.context.conversation_id,
            request.context.principal_id,
        )
        if state is None:
            raise AgentSessionStateError("待结束的面试会话不存在")
        if state.deadlineAt is not None and state.deadlineAt <= datetime.now(timezone.utc):
            return await self.closeInterview(request, state, "INACTIVITY_TIMEOUT")
        return await self.completeInterview(request, state, False)

    async def pauseByCapability(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """处理 Java 明确的暂停请求，避免依赖自然语言意图分类器判断控制指令。"""
        state = await self.repository.loadState(
            request.context.conversation_id,
            request.context.principal_id,
        )
        if state is None:
            raise AgentSessionStateError("待暂停的面试会话不存在")
        return await self.pauseInterview(request, state)

    async def closeByCapability(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """处理前端明确关闭面试的请求；关闭只清理状态，不生成评价也不保留历史。"""
        state = await self.repository.loadState(
            request.context.conversation_id,
            request.context.principal_id,
        )
        if state is None:
            return self.buildClosedResponse(request, "ALREADY_CLOSED")
        return await self.closeInterview(request, state, "USER_CLOSED")

    async def closeInterview(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        reason: str,
    ) -> AgentOperationResponse:
        """关闭未完成面试并物理删除其会话数据；自动超时和用户主动关闭复用同一条无历史路径。"""
        if state.status in {InterviewStatus.COMPLETED, InterviewStatus.AUTO_TERMINATED}:
            # 已完成会话可能已写入长期面试记忆，删除历史时必须同步删除该记忆并重建用户总览。
            await self.memoryService.deleteInterviewMemory(state.userId, state.sessionId)
        deleted = await self.repository.deleteSession(state.sessionId, state.userId)
        if not deleted:
            return self.buildClosedResponse(request, "ALREADY_CLOSED")
        # 先完成数据库物理删除，避免正在执行的回合被错误释放 Redis 租约后继续写回历史记录。
        try:
            await self.memoryService.discardSessionRuntime(state.sessionId)
            await self.ragService.clearSessionCache(state.sessionId)
        except Exception:
            # 会话权威数据已删除；缓存清理失败只能等待 TTL，不能把关闭结果错误报告为失败。
            pass
        return self.buildClosedResponse(request, reason)

    async def terminateExpiredSessions(self) -> None:
        """由后台任务定期强制结束长期无输入的会话，防止 Redis 和数据库状态永久悬挂。"""
        for state in await self.repository.loadExpiredSessions(self.inactiveMinutes * 60):
            request = AgentOperationRequest.model_validate({
                "context": {
                    "apiVersion": "v1",
                    "requestId": f"auto-timeout-{uuid4().hex}",
                    "runId": f"auto-timeout-{uuid4().hex}",
                    "principalId": state.userId,
                    "conversationId": state.sessionId,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "mode": "conversation",
                "prompt": "系统检测到会话超时，结束面试。",
                "stateVersion": state.stateVersion,
            })
            try:
                await self.closeInterview(request, state, "INACTIVITY_TIMEOUT")
            except Exception:
                continue

    async def resolveIntent(self, request: AgentOperationRequest, state: InterviewSessionState) -> InterviewIntent:
        """用受限 JSON 分类自然语言控制意图，普通回答默认被安全地归入回答处理。"""
        payload = await self.invokeStructured(
            "Interview/interviewSessionIntent.txt",
            {
                "currentStatus": state.status.value,
                "currentStage": state.currentStage.value,
                "userPrompt": request.prompt,
            },
            InterviewIntentDecision,
        )
        return payload.intent

    async def createPlan(
        self,
        request: AgentOperationRequest,
        targetRole: str,
        difficulty: Literal["EASY", "MEDIUM", "HARD"],
        resumeId: str | None,
        openingAnswer: str | None = None,
    ) -> InterviewPlan:
        """基于长期记忆和一次性初始化数据生成稳定计划，缺失简历时使用保守通用策略。"""
        memory = await self.memoryService.repository.loadLongTermMemory(
            request.context.principal_id,
            resumeId,
        )
        resumeDetail = await self.memoryService.repository.loadResumeMemoryDetail(
            request.context.principal_id,
            resumeId,
        )
        return await self.invokeStructured(
            "Interview/interviewPlanner.txt",
            {
                "targetRole": targetRole,
                "difficulty": difficulty,
                "resumeId": resumeId,
                "userProfile": memory.userProfile,
                "resumeSummary": memory.resumeMemory,
                "resumeEvaluation": resumeDetail,
                "historicalInterviewSummary": memory.interviewOverview,
                "openingAnswer": openingAnswer,
                "requestData": request.data,
            },
            InterviewPlan,
        )

    async def evaluateAnswer(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        answer: str,
    ) -> InterviewEvaluation:
        """先独立评价当前回答，明确禁止该节点顺便改变面试流程。"""
        memory = await self.memoryService.repository.loadLongTermMemory(state.userId, state.resumeId)
        resumeDetail = await self.memoryService.repository.loadResumeMemoryDetail(state.userId, state.resumeId)
        return await self.invokeStructured(
            "Interview/interviewEvaluation.txt",
            {
                "currentStage": state.currentStage.value,
                "currentTopic": state.currentTopic,
                "currentQuestion": state.currentQuestion,
                "candidateAnswer": answer,
                "currentQuestionEvidence": state.currentQuestionEvidence,
                "resumeSummary": memory.resumeMemory,
                "resumeEvaluation": resumeDetail,
                "userProfile": memory.userProfile,
                "recentTurns": [item.model_dump(mode="json") for item in state.turns[-5:]],
            },
            InterviewEvaluation,
        )

    async def routeAnswer(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        evaluation: InterviewEvaluation,
        allowedActions: set[InterviewAction],
    ) -> InterviewRoute:
        """让模型仅在代码给出的动作白名单内选择下一步，不允许跳过政策约束。"""
        return await self.invokeStructured(
            "Interview/interviewRouting.txt",
            {
                "currentStage": state.currentStage.value,
                "currentTopic": state.currentTopic,
                "evaluation": evaluation.model_dump(mode="json"),
                "allowedActions": sorted(item.value for item in allowedActions),
                "nextStage": self.getNextStage(state.currentStage).value if self.getNextStage(state.currentStage) else None,
                "stagePlan": state.plan.getStage(state.currentStage).model_dump(mode="json"),
                "progress": self.buildProgress(state),
                "explicitCompletionRequested": "结束" in request.prompt or "完成" in request.prompt,
            },
            InterviewRoute,
        )

    async def generateQuestion(
        self,
        state: InterviewSessionState,
        topic: str,
        evidence: list[str],
    ) -> str:
        """在路由已经固定阶段和主题后才生成具体问题，防止 RAG 反向决定业务流程。"""
        memory = await self.memoryService.repository.loadLongTermMemory(state.userId, state.resumeId)
        resumeDetail = await self.memoryService.repository.loadResumeMemoryDetail(state.userId, state.resumeId)
        generated = await self.invokeStructured(
            "Interview/interviewQuestion.txt",
            {
                "stage": state.currentStage.value,
                "topic": topic,
                "difficulty": state.difficulty,
                "askedQuestions": state.askedQuestionCatalog,
                "recentTurns": [item.model_dump(mode="json") for item in state.turns[-5:]],
                "resumeSummary": memory.resumeMemory,
                "resumeEvaluation": resumeDetail,
                "ragEvidence": evidence,
            },
            InterviewQuestion,
        )
        return generated.question

    async def generateSummary(self, state: InterviewSessionState) -> InterviewSummary:
        """基于完整面试记录生成最终评估，避免只根据最后一轮得出结论。"""
        return await self.invokeStructured(
            "Interview/interviewSummary.txt",
            {
                "targetRole": state.targetRole,
                "difficulty": state.difficulty,
                "plan": state.plan.model_dump(mode="json"),
                "turns": [item.model_dump(mode="json") for item in state.turns],
            },
            InterviewSummary,
        )

    async def retrieveQuestionEvidence(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        topic: str,
    ) -> list[str]:
        """以已确定的主题检索题目素材；检索失败降级为空资料而不阻断面试。"""
        try:
            enriched = request.model_copy(update={
                "data": {**request.data, "query": topic},
            })
            context = AgentContext(
                request=enriched,
                skill=SkillDefinition(taskType=AgentTaskType.INTERVIEW_TURN, systemPrompt="", ragEnabled=True),
            )
            return await self.ragService.retrieveKnowledge(context)
        except Exception:
            return []

    def getAllowedActions(
        self,
        state: InterviewSessionState,
        evaluation: InterviewEvaluation,
    ) -> set[InterviewAction]:
        """依据硬题量、阶段覆盖和评分计算白名单，使模型不能越过业务边界。"""
        if state.currentStage == InterviewStage.OPENING:
            return {InterviewAction.NEXT_STAGE}
        if state.totalQuestionCount >= 20:
            return {InterviewAction.END_INTERVIEW}
        stagePlan = state.plan.getStage(state.currentStage)
        actions: set[InterviewAction] = set()
        if evaluation.score <= 60 and state.followupCount < stagePlan.maxFollowupsPerQuestion:
            actions.add(InterviewAction.FOLLOW_UP)
        currentStageCount = state.stageQuestionCounts.get(state.currentStage.value, 0)
        canAskPrimary = currentStageCount < stagePlan.maxPrimaryQuestions
        if state.currentStage == InterviewStage.CODING and currentStageCount >= 1 and evaluation.score >= 40:
            canAskPrimary = False
        if canAskPrimary:
            actions.add(InterviewAction.NEXT_QUESTION)
        nextStage = self.getNextStage(state.currentStage)
        minimumReached = currentStageCount >= min(2, stagePlan.maxPrimaryQuestions)
        if nextStage is not None and minimumReached:
            actions.add(InterviewAction.NEXT_STAGE)
        if state.totalQuestionCount >= 19 or nextStage is None:
            actions.add(InterviewAction.END_INTERVIEW)
        return actions or {InterviewAction.END_INTERVIEW}

    def normalizeRoute(
        self,
        state: InterviewSessionState,
        evaluation: InterviewEvaluation,
        route: InterviewRoute,
        allowedActions: set[InterviewAction],
    ) -> InterviewRoute:
        """对模型路由实施最后一道政策校验，并为缺少主题的合法路径提供计划内回退。"""
        action = route.action if route.action in allowedActions else self.selectFallbackAction(allowedActions)
        if action == InterviewAction.END_INTERVIEW:
            return InterviewRoute(action=action, nextTopic=None)
        if action == InterviewAction.NEXT_STAGE:
            nextStage = self.getNextStage(state.currentStage)
            if nextStage is None or nextStage == InterviewStage.SUMMARY:
                return InterviewRoute(action=InterviewAction.END_INTERVIEW, nextTopic=None)
            topic = route.nextTopic or self.defaultTopic(state, nextStage)
            return InterviewRoute(action=action, nextTopic=topic)
        if action == InterviewAction.FOLLOW_UP:
            topic = route.nextTopic or state.currentTopic or "当前问题的关键缺口"
            return InterviewRoute(action=action, nextTopic=topic)
        return InterviewRoute(action=action, nextTopic=route.nextTopic or self.defaultTopic(state, state.currentStage))

    def applyRoute(self, state: InterviewSessionState, route: InterviewRoute) -> None:
        """根据已经校验的路由迁移阶段和问题计数，模型输出不能直接修改这些字段。"""
        if route.action == InterviewAction.NEXT_STAGE:
            nextStage = self.getNextStage(state.currentStage)
            if nextStage is None:
                raise AgentSessionStateError("当前阶段不存在后续可执行阶段")
            state.currentStage = nextStage
            state.primaryQuestionCount = 0
            state.followupCount = 0
        elif route.action == InterviewAction.FOLLOW_UP:
            state.followupCount += 1
        else:
            state.followupCount = 0
        state.currentTopic = route.nextTopic

    def registerQuestion(
        self,
        state: InterviewSessionState,
        question: str,
        evidence: list[str],
        route: InterviewRoute,
    ) -> None:
        """登记一条已发出的新问题，统一按总预算、阶段预算和主题预算计数。"""
        if state.totalQuestionCount >= 20:
            raise AgentSessionStateError("面试总题量已达到上限")
        if route.action != InterviewAction.FOLLOW_UP:
            state.primaryQuestionCount += 1
            state.totalPrimaryQuestionCount += 1
            state.stageQuestionCounts[state.currentStage.value] = state.stageQuestionCounts.get(state.currentStage.value, 0) + 1
        state.totalQuestionCount += 1
        if state.currentTopic:
            state.topicQuestionCounts[state.currentTopic] = state.topicQuestionCounts.get(state.currentTopic, 0) + 1
        state.currentQuestion = question
        state.currentQuestionEvidence = evidence[:8]
        state.askedQuestionCatalog.append(question)

    def createTurn(
        self,
        state: InterviewSessionState,
        runId: str,
        answer: str,
        evaluation: InterviewEvaluation,
        route: InterviewRoute,
    ) -> InterviewTurn:
        """将当前问答和评价固化为一条可审计回合，后续总结只读取已接受的记录。"""
        return InterviewTurn(
            turnId=uuid4().hex,
            runId=runId,
            stage=state.currentStage,
            topic=state.currentTopic,
            question=state.currentQuestion or "",
            answer=self.dataMasker.maskText(answer),
            evaluation=evaluation,
            action=route.action,
        )

    async def finishAnsweredInterview(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        turn: InterviewTurn,
    ) -> AgentOperationResponse:
        """在回答已评价后结束面试，确保最终报告包含最后一轮表现。"""
        state.status = InterviewStatus.COMPLETING
        summary = await self.generateSummary(state)
        state.finalEvaluation = summary
        state.status = InterviewStatus.COMPLETED
        state.currentStage = InterviewStage.SUMMARY
        state.currentQuestion = None
        state.currentTopic = None
        state.stateVersion = request.state_version + 1
        response = self.buildResponse(request, state, {
            "type": "INTERVIEW_SUMMARY",
            "finalEvaluation": summary.model_dump(mode="json"),
            "evaluation": {
                "summary": turn.evaluation.evaluationSummary,
                "score": turn.evaluation.score,
            },
            "progress": self.buildProgress(state),
        })
        await self.repository.commitState(
            state,
            request.context.run_id,
            request.state_version,
            response.model_dump_json(by_alias=True),
            self.dataMasker.maskText(request.prompt),
            self.dataMasker.maskText(summary.summary),
            turn,
        )
        await self.persistCompletionMemory(state)
        await self.clearInterviewRagState(state.sessionId)
        return response

    async def persistControlTransition(
        self,
        request: AgentOperationRequest,
        state: InterviewSessionState,
        targetStatus: InterviewStatus,
        responseType: str,
    ) -> AgentOperationResponse:
        """提交暂停或恢复等不调用出题模型的控制状态变化，并保留幂等保障。"""
        claim = await self.repository.claimRun(state.sessionId, state.userId, request.context.run_id, request.state_version)
        if claim != "PROCESSING":
            replay = await self.repository.loadRunResult(request.context.run_id, state.sessionId, state.userId)
            if replay is not None:
                return AgentOperationResponse.model_validate(replay)
            raise AgentSessionStateError("控制任务仍在执行")
        try:
            state.status = targetStatus
            state.lastActivityAt = datetime.now(timezone.utc)
            state.deadlineAt = state.lastActivityAt + timedelta(minutes=self.inactiveMinutes)
            state.stateVersion = request.state_version + 1
            response = self.buildResponse(request, state, {
                "type": responseType,
                "content": state.currentQuestion,
                "progress": self.buildProgress(state),
            })
            await self.repository.commitState(
                state,
                request.context.run_id,
                request.state_version,
                response.model_dump_json(by_alias=True),
            )
            return response
        except Exception as error:
            response = self.buildFailureResponse(request, error)
            await self.repository.failRun(state.sessionId, request.context.run_id, response.model_dump_json(by_alias=True))
            raise

    async def persistCompletionMemory(self, state: InterviewSessionState) -> None:
        """在最终状态已经提交后尽力写入长期记忆，失败不回滚已完成面试。"""
        if state.finalEvaluation is None:
            return
        try:
            await self.memoryService.saveInterviewCompletion(
                state.userId,
                state.sessionId,
                state.finalEvaluation.model_dump(mode="json"),
            )
        except Exception:
            return

    async def clearInterviewRagState(self, sessionId: str) -> None:
        """在面试结束后清理临时检索缓存和来源追踪，避免会话数据长期保留。"""
        try:
            await self.ragService.clearSessionCache(sessionId)
            await self.ragService.deleteSessionSources(sessionId)
        except Exception:
            return

    async def invokeStructured(self, promptPath: str, payload: dict[str, object], schema):
        """加载外置提示词、调用统一 LLM 服务并用 Pydantic 严格验证每个节点输出。"""
        messages = [
            {"role": "system", "content": self.promptLoader.loadPrompt(promptPath)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        try:
            raw = await self.llmService.requestJson(messages, temperature=0)
            return schema.model_validate(raw)
        except Exception as error:
            if isinstance(error, LlmOutputSchemaError):
                raise
            raise LlmOutputSchemaError(f"工作流节点输出不符合 {schema.__name__} 结构") from error

    def buildResponse(self, request: AgentOperationRequest, state: InterviewSessionState, data: dict[str, object]) -> AgentOperationResponse:
        """构建只含通用关联字段和业务 data 的对外响应，避免泄露内部路由与检索信息。"""
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=AgentResultStatus.SUCCESS_WITH_DATA,
            status="COMPLETED",
            state_version=state.stateVersion,
            data=data,
        )

    def buildFailureResponse(self, request: AgentOperationRequest, error: Exception) -> AgentOperationResponse:
        """为已占用的 run 构建稳定失败响应，使网络重试可以读取同一错误结果。"""
        statusCode = error.status_code if hasattr(error, "status_code") else AgentResultStatus.AGENT_EXECUTION_FAILED
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=statusCode,
            status="FAILED",
            state_version=request.state_version,
            data=None,
            error=AgentError(type=type(error).__name__, message=str(error), retryable=getattr(error, "retryable", False)),
        )

    def buildClosedResponse(self, request: AgentOperationRequest, reason: str) -> AgentOperationResponse:
        """构建关闭确认响应，调用方据此删除自身展示层记录而不是将其展示为完成的面试历史。"""
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=AgentResultStatus.SUCCESS_WITH_DATA,
            status="COMPLETED",
            state_version=request.state_version + 1,
            data={"type": "INTERVIEW_CLOSED", "reason": reason},
        )

    def buildProgress(self, state: InterviewSessionState) -> dict[str, object]:
        """构建允许前端展示的进度投影，不暴露提示词、检索证据或路由推理。"""
        return {
            "status": state.status.value,
            "currentStage": state.currentStage.value,
            "currentTopic": state.currentTopic,
            "currentPrimaryQuestionCount": state.primaryQuestionCount,
            "totalPrimaryQuestionCount": state.totalPrimaryQuestionCount,
            "currentFollowupCount": state.followupCount,
            "totalQuestionCount": state.totalQuestionCount,
            "questionBudget": 20,
        }

    def getNextStage(self, stage: InterviewStage) -> InterviewStage | None:
        """按固定顺序获取后续阶段，SUMMARY 后不再生成普通问题。"""
        stages = list(InterviewStage)
        index = stages.index(stage)
        return stages[index + 1] if index + 1 < len(stages) else None

    def defaultTopic(self, state: InterviewSessionState, stage: InterviewStage) -> str:
        """当路由节点未给出主题时从已校验计划中选择首个主题，避免使用模型占位文本。"""
        topics = state.plan.getStage(stage).topics
        return topics[0] if topics else f"{stage.value} 阶段核心能力"

    def selectFallbackAction(self, allowedActions: set[InterviewAction]) -> InterviewAction:
        """在模型越界时按安全优先级选择确定性回退动作，保证工作流仍可继续。"""
        for action in (
            InterviewAction.NEXT_STAGE,
            InterviewAction.NEXT_QUESTION,
            InterviewAction.FOLLOW_UP,
            InterviewAction.END_INTERVIEW,
        ):
            if action in allowedActions:
                return action
        return InterviewAction.END_INTERVIEW

    def readDifficulty(self, value: object) -> Literal["EASY", "MEDIUM", "HARD"]:
        """校验一次性初始化难度，非法值回退为稳定默认值而非把异常值交给模型。"""
        return value if value in {"EASY", "MEDIUM", "HARD"} else "MEDIUM"
