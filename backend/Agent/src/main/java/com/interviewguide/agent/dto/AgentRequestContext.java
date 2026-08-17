package com.interviewguide.agent.dto;

import java.time.Instant;

public record AgentRequestContext(
        String apiVersion,
        String requestId,
        String runId,
        String principalId,
        String conversationId,
        Instant timestamp
) {
}
