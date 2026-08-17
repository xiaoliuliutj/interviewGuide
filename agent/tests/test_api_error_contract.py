from agent.Common.Exceptions.AgentException import LlmTimeoutError
from agent.Common.AgentResults import AgentResultStatus
from agent.Api.LLMApi import createFailureResponse
from agent.Common.AgentRequest import AgentOperationRequest


def testFailureResponseKeepsAgentCodeAndChineseMessage() -> None:
    """验证 Python 错误会以稳定错误码、中文说明和重试属性传递给 Java。"""
    request = AgentOperationRequest.model_validate({
        "context": {
            "apiVersion": "v1",
            "requestId": "request-error-1",
            "runId": "run-error-1",
            "principalId": "user-1",
            "conversationId": "session-1",
            "timestamp": "2026-08-17T10:00:00Z",
        },
        "prompt": "测试超时异常",
    })
    response = createFailureResponse(request, LlmTimeoutError("provider timeout"))
    assert response.status_code == AgentResultStatus.LLM_REQUEST_TIMEOUT
    assert response.error is not None
    assert response.error.message == "大模型请求超。"
    assert response.error.retryable is True


def testResumeCapabilitiesUseStableProtocolNames() -> None:
    """验证简历重分析、下载和删除不会依赖 Java 内部类名或任务枚举。"""
    for capability in ("resume.reanalyze", "resume.download", "resume.delete"):
        request = AgentOperationRequest.model_validate({
            "context": {
                "apiVersion": "v1",
                "requestId": f"request-{capability}",
                "runId": f"run-{capability}",
                "principalId": "user-1",
                "conversationId": "resume-1",
                "timestamp": "2026-08-17T10:00:00Z",
            },
            "mode": "capability",
            "capability": capability,
            "data": {"resumeId": "resume-1", "targetRole": "Java 后端"},
        })
        assert request.task_type.value.startswith("RESUME_")
