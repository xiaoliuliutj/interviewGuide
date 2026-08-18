from fastapi import FastAPI, Request

from agent.Common.AgentRequest import AgentOperationRequest
from agent.Common.Exceptions.AgentException import AgentException, AgentRequestContractError
from agent.Common.AgentResults import AgentError, AgentOperationResponse
from agent.Common.AgentErrorCatalog import getAgentErrorMessage


def registerCapabilityApi(app: FastAPI) -> None:
    """注册面向 Java 的非 LLM capability 接口。"""

    @app.post("/internal/v1/capabilities", response_model=AgentOperationResponse)
    async def executeCapability(payload: AgentOperationRequest, request: Request) -> AgentOperationResponse:
        """执行。"capability 标识的文档、知识库和会话生命周期操作。"""
        try:
            if payload.mode != "capability":
                raise AgentRequestContractError("capabilities 接口仅接收 capability 请求")
            return await request.app.state.agentService.dispatch(payload)
        except AgentException as error:
            return AgentOperationResponse(
                api_version=payload.context.api_version,
                request_id=payload.context.request_id,
                run_id=payload.context.run_id,
                principal_id=payload.context.principal_id,
                conversation_id=payload.context.conversation_id,
                status_code=error.status_code,
                status="FAILED",
                state_version=payload.state_version,
                data=None,
                error=AgentError(type=type(error).__name__, message=getAgentErrorMessage(error.status_code), retryable=error.retryable),
            )
