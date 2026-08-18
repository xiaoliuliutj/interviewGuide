package com.interviewguide.agent.client;

public class AgentClientException extends RuntimeException {
    private final int agentCode;
    private final boolean retryable;

    public AgentClientException(String message) {
        this(400, message, true, null);
    }

    public AgentClientException(String message, Throwable cause) {
        this(400, message, true, cause);
    }

    /** 保留 HTTP 适配阶段识别出的 Agent 状态，交由统一可靠性层继续处理。 */
    public AgentClientException(int agentCode, String message, boolean retryable) {
        this(agentCode, message, retryable, null);
    }

    public AgentClientException(int agentCode, String message, boolean retryable, Throwable cause) {
        super(message, cause);
        this.agentCode = agentCode;
        this.retryable = retryable;
    }

    public int getAgentCode() {
        return agentCode;
    }

    public boolean isRetryable() {
        return retryable;
    }
}
