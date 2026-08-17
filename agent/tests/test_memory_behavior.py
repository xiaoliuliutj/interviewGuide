"""记忆模块的无外部依赖行为测试。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

from agent.Agents.AgentLoop import AgentLoop
from agent.Common.AgentModels import AgentLoopCommand, AgentMessage, LlmResponse, SkillDefinition
from agent.Agents.AgentResponse import ResponseValidator
from agent.Memory.memoryRuntime import MemoryRuntime
from agent.Common.AgentRequest import AgentOperationRequest
from agent.utils.security.data_masker import DataMasker


class MemoryServiceStub:
    """提供 AgentLoop 测试所需的最小记忆网关，并记录回合调用顺序。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def loadMemory(self, context):
        return [AgentMessage(role="assistant", content="历史回答")]

    async def loadRunResult(self, runId, userId, sessionId):
        return None

    async def startTurn(self, context):
        self.calls.append("start")
        return "PROCESSING"

    async def renewTurnLease(self, context):
        self.calls.append("renew")

    async def finishTurn(self, context, content):
        self.calls.append("finish")
        return 1

    async def saveRunResult(self, response):
        self.calls.append("save")

    async def abortTurn(self, context):
        self.calls.append("abort")

    async def initializeSession(self, context):
        return None

    async def deleteResumeMemory(self, userId, resumeId):
        return None

    async def deleteInterviewMemory(self, userId, sessionId):
        return None

    async def saveResumeEvaluation(self, userId, resumeId, evaluation):
        return None

    async def saveInterviewCompletion(self, userId, sessionId, result):
        return None

    async def saveUserProfile(self, userId, profile):
        return None


class LlmServiceStub:
    """校验消息顺序后返回确定的最终结果。"""

    async def generateAgentResponse(self, context):
        assert context.messages[-1].role == "user"
        assert context.messages[-1].content == '{"answer": "当前回答"}'
        assert any(message.content == "历史回答" for message in context.messages[:-1])
        return LlmResponse(finalData={"reply": "ok"})


class SkillServiceStub:
    """为测试提供启用记忆的面试技能。"""

    async def resolveSkill(self, taskType):
        return SkillDefinition(taskType=taskType, systemPrompt="面试规则", memoryEnabled=True)


class ToolServiceStub:
    """测试中不允许模型调用工具。"""

    async def executeTool(self, toolCall, context):
        raise AssertionError("当前测试不应触发工具调用")


class RagServiceStub:
    """测试中返回空检索结果。"""

    async def retrieveKnowledge(self, context):
        return []


def testInterviewTurnUsesMemoryBeforeCurrentRequest() -> None:
    """验证面试回合按记忆在前、当前请求在后的顺序组装消息并正确持久化。"""

    async def executeTest() -> None:
        request = AgentOperationRequest.model_validate(
            {
                "context": {
                    "apiVersion": "v1",
                    "requestId": "request-1",
                    "runId": "run-1",
                    "principalId": "user-1",
                    "conversationId": "session-1",
                    "timestamp": datetime.now().isoformat(),
                },
                "mode": "conversation",
                "prompt": "当前回答",
            }
        )
        memoryService = MemoryServiceStub()
        loop = AgentLoop(
            LlmServiceStub(),
            SkillServiceStub(),
            ToolServiceStub(),
            memoryService,
            RagServiceStub(),
            ResponseValidator(),
        )
        response = await loop.run(AgentLoopCommand(request, request.payload))
        assert response.status == "COMPLETED"
        assert response.state_version == 1
        assert memoryService.calls == ["start", "renew", "finish", "save"]

    asyncio.run(executeTest())


def testRedisLockFailureFallsBackToDatabaseClaim() -> None:
    """验证 Redis 锁故障不会阻断数据库并发控制和回合启动。"""

    class RedisFailureStore:
        async def acquireRun(self, sessionId, runId):
            raise RuntimeError("Redis unavailable")

    class RepositoryStub:
        async def claimRun(self, *values):
            return "PROCESSING"

    async def executeTest() -> None:
        service = MemoryRuntime.__new__(MemoryRuntime)
        service.sessionStore = RedisFailureStore()
        service.repository = RepositoryStub()
        context = SimpleNamespace(
            request=SimpleNamespace(
                context=SimpleNamespace(conversation_id="session-1", run_id="run-1", principal_id="user-1"),
                task_type=SimpleNamespace(value="CONVERSATION"),
                state_version=0,
            ),
            redisLeaseEnabled=True,
        )
        assert await service.startTurn(context) == "PROCESSING"
        assert context.redisLeaseEnabled is False

    asyncio.run(executeTest())


def testSensitiveFieldsAreMaskedBeforePersistence() -> None:
    """验证手机号、邮箱和身份证号不会以原文形式进入记忆持久化数据。"""

    masker = DataMasker()
    masked = masker.maskObject(
        {
            "phone": "13812345678",
            "email": "candidate@example.com",
            "identity": "11010519491231002X",
        }
    )
    serialized = str(masked)
    assert "13812345678" not in serialized
    assert "candidate@example.com" not in serialized
    assert "11010519491231002X" not in serialized
