package com.interviewguide.agent.dto;

public record AgentError(
        String type,
        String message,
        boolean retryable
) {
}
