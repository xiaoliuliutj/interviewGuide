from agent.Agents.models import LlmResponse
from agent.Common.Exceptions.agent_exception import LlmOutputSchemaError
from agent.Common.results import AgentOperationResponse, AgentResultStatus
from agent.api.contracts import AgentOperationRequest


class ResponseValidator:
    """Validates structural protocol correctness without judging generated content quality."""

    def validateModelResponse(self, response: LlmResponse) -> None:
        """Require a model turn to choose exactly one valid next action or final result."""
        hasFinalData = response.finalData is not None
        hasToolCall = response.toolCall is not None
        if hasFinalData == hasToolCall:
            raise LlmOutputSchemaError(
                "大模型响应必须且只能包含 finalData 或 toolCall 之一",
            )
        if hasFinalData and not isinstance(response.finalData, dict):
            raise LlmOutputSchemaError("大模型 finalData 必须是 JSON 对象")
        if hasToolCall:
            if not response.toolCall.name.strip():
                raise LlmOutputSchemaError("大模型工具调用必须包含工具名称")
            if not isinstance(response.toolCall.arguments, dict):
                raise LlmOutputSchemaError("大模型工具参数必须是 JSON 对象")

    def validateFinalResponse(
        self,
        request: AgentOperationRequest,
        response: AgentOperationResponse,
    ) -> None:
        """Verify response identity and success/result-shape consistency before Java receives it."""
        matchesRequest = (
            response.request_id == request.context.request_id
            and response.run_id == request.context.run_id
            and response.principal_id == request.context.principal_id
            and response.conversation_id == request.context.conversation_id
        )
        if not matchesRequest:
            raise LlmOutputSchemaError("Agent 响应关联信息与输入请求不一致")

        if response.status_code == AgentResultStatus.SUCCESS_WITH_DATA and response.data is None:
            raise LlmOutputSchemaError("成功且包含数据的响应必须提供 data")
