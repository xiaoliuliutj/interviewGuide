from agent.Common.AgentModels import LlmResponse
from agent.Common.AgentRequest import AgentOperationRequest
from agent.Common.AgentResults import AgentOperationResponse, AgentResultStatus
from agent.Common.Exceptions.AgentException import LlmOutputSchemaError


class ResponseValidator:
    """校验模型输出和最终响应的结构一致性。"""

    def validateModelResponse(self, response: LlmResponse) -> None:
        """要求模型每轮只返回工具调用或最终结果中的一种。"""
        hasFinalData = response.finalData is not None
        hasToolCall = response.toolCall is not None
        if hasFinalData == hasToolCall:
            raise LlmOutputSchemaError("大模型响应必须且只能包含 finalData 或 toolCall 之一")
        if hasFinalData and not isinstance(response.finalData, dict):
            raise LlmOutputSchemaError("大模型 finalData 必须是 JSON 对象")
        if hasToolCall and not response.toolCall.name.strip():
            raise LlmOutputSchemaError("大模型工具调用必须包含工具名称")
        if hasToolCall and not isinstance(response.toolCall.arguments, dict):
            raise LlmOutputSchemaError("大模型工具参数必须是 JSON 对象")

    def validateFinalResponse(self, request: AgentOperationRequest, response: AgentOperationResponse) -> None:
        """在对外响应前核对关联标识和成功结果的数据要求。"""
        if (response.request_id != request.context.request_id or response.run_id != request.context.run_id
                or response.principal_id != request.context.principal_id
                or response.conversation_id != request.context.conversation_id):
            raise LlmOutputSchemaError("Agent 响应关联信息与输入请求不一致")
        if response.status_code == AgentResultStatus.SUCCESS_WITH_DATA and response.data is None:
            raise LlmOutputSchemaError("成功且包含数据的响应必须提供 data")
