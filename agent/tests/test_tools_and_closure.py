import asyncio
import json

from agent.Common.AgentModels import AgentContext, SkillDefinition, ToolCall
from agent.Common.AgentResults import AgentTaskType
from agent.Tools.toolsService import ToolService
from agent.Workflows.Interview.interviewModels import InterviewSessionState, InterviewStage
from agent.Workflows.Interview.interviewWorkflow import InterviewWorkflow
from agent.Common.AgentRequest import AgentOperationRequest
from agent.tests.test_workflow_core import buildPlan


def buildRequest() -> AgentOperationRequest:
    """构造一个通用会话请求，供关闭能力与工具执行测试复用。"""
    return AgentOperationRequest.model_validate({
        "context": {
            "apiVersion": "v1",
            "requestId": "request-close-1",
            "runId": "run-close-1",
            "principalId": "user-1",
            "conversationId": "session-1",
            "timestamp": "2026-08-17T10:00:00Z",
        },
        "mode": "capability",
        "capability": "interview.close",
        "stateVersion": 2,
    })


def testParseDocumentToolUsesRegisteredHandler() -> None:
    """验证字符串工具名会通过注册表映射到真实文档解析函数，而不是进入占位异常。"""
    toolService = ToolService()
    context = AgentContext(
        request=buildRequest(),
        skill=SkillDefinition(
            taskType=AgentTaskType.CONVERSATION,
            systemPrompt="test",
        ),
    )
    result = asyncio.run(toolService.executeTool(
        ToolCall(
            name="parseDocument",
        arguments={"content": "# \u6280\u672f\u6808\nJava \u4e0e Spring Boot", "fileName": "resume.md"},
        ),
        context,
    ))
    payload = json.loads(result.content)
    assert result.succeeded is True
    assert payload["sections"][0]["headingPath"] == "技术栈"


def testExplicitCloseDeletesWorkflowWithoutEvaluation() -> None:
    """验证显式关闭只删除未完成会话并返回关闭确认，不触。"LLM 总结或长期记忆写入。"""
    state = InterviewSessionState(
        sessionId="session-1",
        userId="user-1",
        targetRole="Java 后端",
        plan=buildPlan(),
        currentStage=InterviewStage.FUNDAMENTAL,
        currentQuestion="解释线程池的核心参数。",
        stateVersion=2,
    )

    class FakeRepository:
        deleted = False

        async def loadState(self, sessionId, userId):
            return state

        async def deleteSession(self, sessionId, userId):
            self.deleted = True
            return True

    class FakeMemory:
        discarded = False

        async def discardSessionRuntime(self, sessionId):
            self.discarded = True

    class FakeRag:
        cleared = False

        async def clearSessionCache(self, sessionId):
            self.cleared = True

    repository = FakeRepository()
    memory = FakeMemory()
    rag = FakeRag()
    workflow = InterviewWorkflow(None, memory, rag, repository)
    response = asyncio.run(workflow.closeByCapability(buildRequest()))
    assert response.data == {"type": "INTERVIEW_CLOSED", "reason": "USER_CLOSED"}
    assert repository.deleted is True
    assert memory.discarded is True
    assert rag.cleared is True


def testInterviewWorkflowDefaultsToSixHoursInactivity() -> None:
    """验证自动关闭阈值使用六小时无推进，而不是旧的三十分钟会话超时。"""
    workflow = InterviewWorkflow(None, None, None, None)
    assert workflow.inactiveMinutes == 360
