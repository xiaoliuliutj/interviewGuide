package com.interviewguide.agent.config;

import com.interviewguide.agent.client.AgentClient;
import com.interviewguide.agent.client.HttpAgentClient;
import com.interviewguide.agent.service.AgentPromptService;
import com.interviewguide.agent.service.AgentRequestFactory;
import com.interviewguide.agent.service.AgentResponseGuard;
import com.interviewguide.agent.service.AgentExceptionHandler;
import com.interviewguide.agent.service.AgentCallService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@AutoConfiguration
@EnableConfigurationProperties(AgentClientProperties.class)
public class AgentClientAutoConfiguration {
    @Bean
    public AgentClient agentClient(
            RestClient.Builder restClientBuilder,
            AgentClientProperties properties
    ) {
        RestClient restClient = restClientBuilder
                .baseUrl(properties.getBaseUrl().toString())
                .build();
        return new HttpAgentClient(restClient);
    }

    /** 注册可被多个业务 Service 复用的请求、提示词和响应支持组件。 */
    @Bean
    public AgentPromptService agentPromptService() {
        return new AgentPromptService();
    }

    /** 注册通用请求信封构造器，业务 Service 仍决定任务和数据内容。 */
    @Bean
    public AgentRequestFactory agentRequestFactory() {
        return new AgentRequestFactory();
    }

    /** 注册 Agent 失败响应转换器，统一保留中文错误码和重试属性。 */
    @Bean
    public AgentResponseGuard agentResponseGuard() {
        return new AgentResponseGuard();
    }

    /** 注册统一 Agent 异常映射，前端可按 Python 错误码定位失败位置。 */
    @Bean
    public AgentExceptionHandler agentExceptionHandler() {
        return new AgentExceptionHandler();
    }

    /** 注册跨业务复用的有限重试与熔断执行器，业务补偿仍留在各自 Service。 */
    @Bean
    public AgentCallService agentCallService(AgentClient agentClient, AgentResponseGuard responseGuard) {
        return new AgentCallService(agentClient, responseGuard);
    }
}
