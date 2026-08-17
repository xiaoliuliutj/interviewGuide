package com.interviewguide.agent.service;

import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;

/**
 * 校验 Agent 响应关联关系并将失败响应转换为 Java 可处理的异常。
 *
 * <p>该能力由多个业务 Service 使用，因此集中实现；它不决定是否重试、降级或如何更新业务状态。</p>
 */
public class AgentResponseGuard {
    /**
     * 确认响应属于当前请求，并在 Agent 明确失败时抛出携带原始错误码的异常。
     */
    public AgentOperationResponse requireSuccess(
            AgentOperationRequest request,
            AgentOperationResponse response
    ) {
        if (response == null) {
            throw new AgentServiceException(400, "Agent 服务未返回响应", true);
        }
        if (!request.context().requestId().equals(response.requestId())
                || !request.context().runId().equals(response.runId())
                || !request.context().principalId().equals(response.principalId())
                || !request.context().conversationId().equals(response.conversationId())) {
            throw new AgentServiceException(402, "Agent 响应关联信息与请求不一致", false);
        }
        if (response.statusCode() != 100 && response.statusCode() != 101) {
            String message = response.error() == null ? "Agent 执行失败" : response.error().message();
            boolean retryable = response.error() != null && response.error().retryable();
            throw new AgentServiceException(response.statusCode(), message, retryable);
        }
        return response;
    }
}
