package com.interviewguide.agent.client;

public class AgentClientException extends RuntimeException {
    public AgentClientException(String message) {
        super(message);
    }

    public AgentClientException(String message, Throwable cause) {
        super(message, cause);
    }
}
