package com.interviewguide.agent.service;

import java.util.Map;

/** 将 Agent 返回的错误码、中文说明和重试属性传递给 Java 业务层。 */
public class AgentServiceException extends RuntimeException {
    private final int agentCode;
    private final boolean retryable;
    private final Map<String, Object> data;

    /** 保存 Agent 已经标准化的错误信息，避免 Java 猜测 Python 内部失败原因。 */
    public AgentServiceException(int agentCode, String message, boolean retryable) {
        this(agentCode, message, retryable, null);
    }

    /** 保存 Agent 失败响应中的业务数据，供异步任务状态对账继续传递具体原因。 */
    public AgentServiceException(int agentCode, String message, boolean retryable, Map<String, Object> data) {
        super(message);
        this.agentCode = agentCode;
        this.retryable = retryable;
        this.data = data;
    }

    public int getAgentCode() {
        return agentCode;
    }

    public boolean isRetryable() {
        return retryable;
    }

    public Map<String, Object> getData() {
        return data;
    }
}
