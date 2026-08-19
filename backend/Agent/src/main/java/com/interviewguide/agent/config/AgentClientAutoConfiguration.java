package com.interviewguide.agent.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewguide.agent.client.AgentClient;
import com.interviewguide.agent.client.HttpAgentClient;
import com.interviewguide.agent.service.AgentCallService;
import com.interviewguide.agent.service.AgentExceptionHandler;
import com.interviewguide.agent.service.AgentRequestFactory;
import com.interviewguide.agent.service.AgentResponseGuard;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

/** Java 仅负责 Agent HTTP 协议、请求关联和错误透传；业务提示词与模型格式由 Agent 管理。 */
@AutoConfiguration
@EnableConfigurationProperties(AgentClientProperties.class)
public class AgentClientAutoConfiguration {
    @Bean
    public AgentClient agentClient(AgentClientProperties properties, ObjectMapper objectMapper) {
        return new HttpAgentClient(properties.getBaseUrl(), objectMapper);
    }

    @Bean
    public AgentRequestFactory agentRequestFactory() {
        return new AgentRequestFactory();
    }

    @Bean
    public AgentResponseGuard agentResponseGuard() {
        return new AgentResponseGuard();
    }

    @Bean
    public AgentExceptionHandler agentExceptionHandler() {
        return new AgentExceptionHandler();
    }

    @Bean
    public AgentCallService agentCallService(AgentClient agentClient, AgentResponseGuard responseGuard) {
        return new AgentCallService(agentClient, responseGuard);
    }
}
