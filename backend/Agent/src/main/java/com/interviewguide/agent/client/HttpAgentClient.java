package com.interviewguide.agent.client;

import com.interviewguide.agent.dto.AgentHealthResponse;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * 使用 HTTP 调用独立 Agent 服务的适配器。
 * 该类只校验通用关联字段，不解析 Agent 的内部业务流程。
 */
public class HttpAgentClient implements AgentClient {
    private final RestClient restClient;
    public HttpAgentClient(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public AgentHealthResponse health() {
        try {
            AgentHealthResponse response = restClient.get()
                    .uri("/internal/v1/health")
                    .retrieve()
                    .body(AgentHealthResponse.class);
            if (response == null) {
                throw new AgentClientException("Agent 健康检查未返回响应");
            }
            return response;
        } catch (RestClientException error) {
            throw new AgentClientException("Agent 健康检查请求失败", error);
        }
    }

    @Override
    public AgentOperationResponse execute(AgentOperationRequest request) {
        try {
            return restClient.post()
                    .uri("capability".equals(request.mode())
                            ? "/internal/v1/capabilities"
                            : "/internal/v1/runs")
                    .body(request)
                    .retrieve()
                    .body(AgentOperationResponse.class);
        } catch (RestClientException error) {
            throw new AgentClientException("Agent 服务请求失败", error);
        }
    }
}
