package com.interviewguide.agent.dto;

import java.util.Map;

public record AgentOperationRequest(
        AgentRequestContext context,
        String mode,
        String capability,
        String prompt,
        Map<String, Object> data,
        long stateVersion
) {
}
