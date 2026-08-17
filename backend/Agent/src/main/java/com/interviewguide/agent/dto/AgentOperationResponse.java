package com.interviewguide.agent.dto;

import java.time.Instant;
import java.util.Map;

public record AgentOperationResponse(
        String apiVersion,
        String requestId,
        String runId,
        String principalId,
        String conversationId,
        int statusCode,
        String status,
        long stateVersion,
        Map<String, Object> data,
        AgentError error,
        Instant timestamp
) {
}
