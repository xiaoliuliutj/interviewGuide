package com.interviewguide.agent.service;

import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentRequestContext;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * 创建跨服务通用请求信封。
 *
 * <p>该组件仅组装协议字段，被多个业务 Service 调用；任务选择、提示词内容和可靠性策略仍由各业务 Service 决定。</p>
 */
public class AgentRequestFactory {
    /**
     * 创建一次 Agent 调用请求。
     *
     * <p>会话任务传入真实 sessionId；非会话任务传入本次请求生成的临时关联标识，Agent 不需要了解 Java 的业务表结构。</p>
     */
    public AgentOperationRequest create(
            String userId,
            String sessionId,
            String runId,
            String mode,
            String capability,
            String prompt,
            Map<String, Object> data,
            long stateVersion
    ) {
        String requestId = UUID.randomUUID().toString();
        AgentRequestContext context = new AgentRequestContext(
                "v1", requestId, runId, userId, sessionId, Instant.now()
        );
        return new AgentOperationRequest(context, mode, capability, prompt, data, stateVersion);
    }
}
