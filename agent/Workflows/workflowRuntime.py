"""统一自然语言入口和业务工作流路由。"""

import json

from agent.Agents.AgentLoop import AgentLoop
from agent.Common.AgentModels import AgentLoopCommand
from agent.Common.Exceptions.AgentException import AgentRequestContractError, LlmOutputSchemaError
from agent.LLM.llmService import LlmService
from agent.Common.PromptService import PromptLoader
from agent.Common.AgentRequest import AgentOperationRequest
from agent.Workflows.Interview.interviewModels import WorkflowIntentDecision
from agent.Workflows.Interview.interviewRepository import InterviewWorkflowRepository
from agent.Workflows.Interview.interviewWorkflow import InterviewWorkflow
from agent.Workflows.Resume.resumeRepository import ResumeWorkflowRepository
from agent.Workflows.Resume.resumeWorkflow import ResumeWorkflow


class WorkflowRuntime:
    """在不暴露内部任务枚举的前提下选择并运行简历或面试工作流。"""

    def __init__(
        self,
        llmService: LlmService,
        agentLoop: AgentLoop,
        interviewWorkflow: InterviewWorkflow,
        resumeWorkflow: ResumeWorkflow,
        interviewRepository: InterviewWorkflowRepository,
        resumeRepository: ResumeWorkflowRepository,
        promptLoader: PromptLoader | None = None,
    ) -> None:
        """注入共享运行时和两个核心工作流，普通对话仍回退到原有 AgentLoop。"""
        self.llmService = llmService
        self.agentLoop = agentLoop
        self.interviewWorkflow = interviewWorkflow
        self.resumeWorkflow = resumeWorkflow
        self.interviewRepository = interviewRepository
        self.resumeRepository = resumeRepository
        self.promptLoader = promptLoader or PromptLoader()

    async def handleConversation(self, request: AgentOperationRequest):
        """优先按已有会话绑定路由，首次请求才调用顶层自然语言分类器。"""
        activeInterview = await self.interviewRepository.loadState(
            request.context.conversation_id,
            request.context.principal_id,
        )
        if activeInterview is not None:
            return await self.interviewWorkflow.handleRequest(request)
        decision = await self.resolveWorkflow(request)
        if decision.workflow == "INTERVIEW":
            return await self.interviewWorkflow.handleRequest(request)
        if decision.workflow == "RESUME_ANALYSIS":
            return await self.resumeWorkflow.handleRequest(request)
        return await self.agentLoop.run(
            AgentLoopCommand(request=request, parsedPayload=request.payload),
        )

    async def handleResumeCapability(self, request: AgentOperationRequest):
        """处理必须携带二进制文件或需要精确任务状态的非对话简历能力。"""
        if request.capability == "resume.upload":
            return await self.resumeWorkflow.upload(request)
        if request.capability == "resume.status":
            return await self.resumeWorkflow.handleRequest(request)
        if request.capability == "resume.reanalyze":
            return await self.resumeWorkflow.reanalyze(request)
        if request.capability == "resume.download":
            return await self.resumeWorkflow.download(request)
        if request.capability == "resume.delete":
            return await self.resumeWorkflow.delete(request)
        raise AgentRequestContractError("不支持的简历 capability")

    async def handleInterviewCapability(self, request: AgentOperationRequest):
        """处理显式结束或关闭面试的确定性生命周期能力，不依赖自然语言意图识别。"""
        if request.capability == "interview.complete":
            return await self.interviewWorkflow.completeByCapability(request)
        if request.capability == "interview.close":
            return await self.interviewWorkflow.closeByCapability(request)
        if request.capability == "interview.pause":
            return await self.interviewWorkflow.pauseByCapability(request)
        raise AgentRequestContractError("不支持的面试 capability")

    async def resolveWorkflow(self, request: AgentOperationRequest) -> WorkflowIntentDecision:
        """调用受限顶层路由提示词，模型只能返回已注册工作流名称。"""
        messages = [
            {"role": "system", "content": self.promptLoader.loadPrompt("Interview/interviewIntentRouter.txt")},
            {"role": "user", "content": json.dumps({"prompt": request.prompt, "data": request.data}, ensure_ascii=False)},
        ]
        try:
            raw = await self.llmService.requestJson(messages, temperature=0)
            decision = WorkflowIntentDecision.model_validate(raw)
        except Exception as error:
            raise LlmOutputSchemaError("自然语言工作流路由结果不符合协议") from error
        if decision.confidence < 0.55:
            raise AgentRequestContractError("无法可靠判断请求类型，请明确说明是开始面试还是分析简历")
        return decision

    async def processResumeJobs(self) -> None:
        """运行简历解析和评估 worker，进程重启后可从数据库继续未完成任务。"""
        await self.resumeWorkflow.processJobs()

    async def processExpiredInterviews(self) -> None:
        """运行面试无输入超时收敛任务，状态变化仍由 Workflow 原子提交。"""
        await self.interviewWorkflow.terminateExpiredSessions()

    async def close(self) -> None:
        """释放工作流独立持有的数据库连接池，不重复关闭共享 LLM 客户端。"""
        await self.interviewRepository.postgresService.close()
        await self.resumeRepository.postgresService.close()
