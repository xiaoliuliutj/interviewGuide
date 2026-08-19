package com.interviewguide.agent.service;

import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import com.interviewguide.common.results.ResultStatus;

/** 校验 Agent 响应协议，并区分业务错误和成功响应的关联关系。 */
public class AgentResponseGuard {
    /** 失败响应优先保留 Agent 状态码；成功响应必须通过请求关联字段校验。 */
    public AgentOperationResponse requireSuccess(
            AgentOperationRequest request,
            AgentOperationResponse response
    ) {
        if (response == null) {
            throw new AgentServiceException(400, ResultStatus.descriptionOf(400), true);
        }
        if (response.statusCode() != 100 && response.statusCode() != 101) {
            String message = response.error() == null || response.error().message() == null
                    ? ResultStatus.descriptionOf(response.statusCode()) : response.error().message();
            boolean retryable = response.error() != null && response.error().retryable();
            throw new AgentServiceException(response.statusCode(), message, retryable, response.data());
        }
        if (!request.context().requestId().equals(response.requestId())
                || !request.context().runId().equals(response.runId())
                || !request.context().principalId().equals(response.principalId())
                || !request.context().conversationId().equals(response.conversationId())) {
            throw new AgentServiceException(402, "Agent 响应关联信息与请求不一致", false);
        }
        return response;
    }
}
