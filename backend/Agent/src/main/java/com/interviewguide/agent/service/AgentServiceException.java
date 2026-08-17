package com.interviewguide.agent.service;

/** 将 Agent 返回的错误码、中文说明和重试属性传递给 Java 业务层。 */
public class AgentServiceException extends RuntimeException {
    private final int agentCode;
    private final boolean retryable;

    /** 保存 Agent 已经标准化的错误信息，避免 Java 猜测 Python 内部失败原因。 */
    public AgentServiceException(int agentCode, String message, boolean retryable) {
        super(message);
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
