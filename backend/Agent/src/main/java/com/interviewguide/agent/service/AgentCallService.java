package com.interviewguide.agent.service;

import com.interviewguide.agent.client.AgentClient;
import com.interviewguide.agent.client.AgentClientException;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import java.time.Instant;

/** 负责 Java 到 Agent 的重试与熔断；不改写 Agent 已确定的业务错误。 */
public class AgentCallService {
    private static final int MAX_ATTEMPTS = 2;
    private static final int CIRCUIT_FAILURE_THRESHOLD = 3;
    private static final long CIRCUIT_COOLDOWN_MILLIS = 30_000L;

    private final AgentClient agentClient;
    private final AgentResponseGuard responseGuard;
    private int consecutiveFailures;
    private Instant circuitOpenUntil;

    public AgentCallService(AgentClient agentClient, AgentResponseGuard responseGuard) {
        this.agentClient = agentClient;
        this.responseGuard = responseGuard;
    }

    /** 对可重试的通信或 Agent 错误最多重试两次，连续失败后短暂熔断。 */
    public synchronized AgentOperationResponse execute(AgentOperationRequest request) {
        if (circuitOpenUntil != null && Instant.now().isBefore(circuitOpenUntil)) {
            throw new AgentServiceException(400, "Agent 服务暂时熔断，请稍后重试", true);
        }
        AgentServiceException lastError = null;
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
                lastError = new AgentServiceException(error.getAgentCode(), error.getMessage(), error.isRetryable());
                if (!error.isRetryable()) {
                    throw lastError;
                }
            }
        }
        consecutiveFailures++;
        if (consecutiveFailures >= CIRCUIT_FAILURE_THRESHOLD) {
            circuitOpenUntil = Instant.now().plusMillis(CIRCUIT_COOLDOWN_MILLIS);
        }
        throw lastError == null
                ? new AgentServiceException(400, "Agent 服务暂时不可用", true)
                : lastError;
    }
}
