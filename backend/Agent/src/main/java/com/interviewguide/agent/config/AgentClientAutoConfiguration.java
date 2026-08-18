package com.interviewguide.agent.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewguide.agent.client.AgentClient;
import com.interviewguide.agent.client.HttpAgentClient;
import com.interviewguide.agent.service.AgentCallService;
import com.interviewguide.agent.service.AgentExceptionHandler;
import com.interviewguide.agent.service.AgentPromptService;
import com.interviewguide.agent.service.AgentRequestFactory;
import com.interviewguide.agent.service.AgentResponseGuard;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

/** 配置 Java 调用独立 Agent 服务所需的公共组件。 */
@AutoConfiguration
@EnableConfigurationProperties(AgentClientProperties.class)
public class AgentClientAutoConfiguration {
    /**
     * 创建唯一的 Agent 通信客户端。
     *
     * <p>显式使用 HTTP/1.1 JSON 请求，确保 Java 与 Uvicorn 的请求体传输行为稳定一致。</p>
     */
    @Bean
    public AgentClient agentClient(AgentClientProperties properties, ObjectMapper objectMapper) {
        return new HttpAgentClient(properties.getBaseUrl(), objectMapper);
    }

    /** 注册跨业务复用的提示词加载组件。 */
    @Bean
    public AgentPromptService agentPromptService() {
        return new AgentPromptService();
    }

    /** 注册统一请求信封构造组件。 */
    @Bean
    public AgentRequestFactory agentRequestFactory() {
        return new AgentRequestFactory();
    }

    /** 注册 Agent 响应协议校验组件。 */
    @Bean
    public AgentResponseGuard agentResponseGuard() {
        return new AgentResponseGuard();
    }

    /** 注册 Agent 异常向前端结果的映射组件。 */
    @Bean
    public AgentExceptionHandler agentExceptionHandler() {
        return new AgentExceptionHandler();
    }

    /** 注册包含有限重试和熔断策略的 Agent 调用服务。 */
    @Bean
    public AgentCallService agentCallService(AgentClient agentClient, AgentResponseGuard responseGuard) {
        return new AgentCallService(agentClient, responseGuard);
    }
}
