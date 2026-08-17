package com.interviewguide.agent.service;

import com.interviewguide.agent.client.AgentClient;
import com.interviewguide.agent.client.AgentClientException;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import java.time.Instant;

/**
 * 执行 Java 侧通用可靠性控制：有限重试和简单熔断。
 *
 * <p>该类不构造 Prompt、不决定业务补偿，也不解释 Agent data；业务 Service 在调用前后负责自身事务和状态。</p>
 */
public class AgentCallService {
    private static final int MAX_ATTEMPTS = 2;
    private static final int CIRCUIT_FAILURE_THRESHOLD = 3;
    private static final long CIRCUIT_COOLDOWN_MILLIS = 30_000L;

    private final AgentClient agentClient;
    private final AgentResponseGuard responseGuard;
    private int consecutiveFailures;
    private Instant circuitOpenUntil;

    /** 保存纯 HTTP Client 和统一响应校验器。 */
    public AgentCallService(AgentClient agentClient, AgentResponseGuard responseGuard) {
        this.agentClient = agentClient;
        this.responseGuard = responseGuard;
    }

    /**
     * 对明确可恢复的网络或 Agent 错误最多尝试两次，并在连续失败后短暂熔断。
     */
    public synchronized AgentOperationResponse execute(AgentOperationRequest request) {
        if (circuitOpenUntil != null && Instant.now().isBefore(circuitOpenUntil)) {
            throw new AgentServiceException(400, "Agent 服务暂时熔断，请稍后重试", true);
        }
        RuntimeException lastError = null;
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                AgentOperationResponse response = responseGuard.requireSuccess(request, agentClient.execute(request));
                consecutiveFailures = 0;
                circuitOpenUntil = null;
                return response;
            } catch (AgentServiceException error) {
                lastError = error;
                if (!error.isRetryable()) {
                    throw error;
                }
            } catch (AgentClientException error) {
                lastError = new AgentServiceException(400, "Agent 服务暂时不可用", true);
            }
        }
        consecutiveFailures++;
        if (consecutiveFailures >= CIRCUIT_FAILURE_THRESHOLD) {
            circuitOpenUntil = Instant.now().plusMillis(CIRCUIT_COOLDOWN_MILLIS);
        }
        throw lastError == null ? new AgentServiceException(400, "Agent 服务暂时不可用", true) : lastError;
    }
}
