package com.interviewguide.agent.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewguide.agent.dto.AgentHealthResponse;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import java.util.Locale;
import org.springframework.http.MediaType;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/** 只负责 HTTP 调用和协议响应读取，不决定业务补偿或降级策略。 */
public class HttpAgentClient implements AgentClient {
    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public HttpAgentClient(RestClient restClient, ObjectMapper objectMapper) {
        this.restClient = restClient;
        this.objectMapper = objectMapper;
    }

    public HttpAgentClient(RestClient restClient) {
        this(restClient, new ObjectMapper());
    }

    @Override
    public AgentHealthResponse health() {
        try {
            AgentHealthResponse response = restClient.get()
                    .uri("/internal/v1/health")
                    .retrieve()
                    .body(AgentHealthResponse.class);
            if (response == null) {
                throw new AgentClientException(400, "Agent 健康检查未返回响应", true);
            }
            return response;
        } catch (ResourceAccessException error) {
            throw createTransportException(error);
        } catch (RestClientResponseException error) {
            throw createHttpException(error);
        } catch (RestClientException error) {
            throw new AgentClientException(400, "Agent 健康检查请求失败", true, error);
        }
    }

    @Override
    public AgentOperationResponse execute(AgentOperationRequest request) {
        try {
            return restClient.post()
                    .uri("capability".equals(request.mode())
                            ? "/internal/v1/capabilities"
                            : "/internal/v1/runs")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(AgentOperationResponse.class);
        } catch (ResourceAccessException error) {
            throw createTransportException(error);
        } catch (RestClientResponseException error) {
            throw createHttpException(error);
        } catch (RestClientException error) {
            throw new AgentClientException(400, "Agent 请求失败", true, error);
        }
    }

    /** 将连接超时和连接不可达转换为统一的 Agent 通信状态。 */
    private AgentClientException createTransportException(ResourceAccessException error) {
        String detail = error.getMessage() == null ? "" : error.getMessage().toLowerCase(Locale.ROOT);
        if (detail.contains("timed out") || detail.contains("timeout")) {
            return new AgentClientException(401, "Agent 服务请求超时", true, error);
        }
        return new AgentClientException(400, "Agent 服务暂时不可用", true, error);
    }

    /** 读取 Agent 标准错误；FastAPI 校验错误映射为协议错误 404，而不是笼统的 400。 */
    private AgentClientException createHttpException(RestClientResponseException error) {
        String body = error.getResponseBodyAsString();
        try {
            JsonNode root = objectMapper.readTree(body);
            if (root.has("statusCode")) {
                int code = root.path("statusCode").asInt(400);
                JsonNode agentError = root.path("error");
                String message = agentError.path("message").asText("Agent 执行失败");
                boolean retryable = agentError.path("retryable").asBoolean(false);
                return new AgentClientException(code, message, retryable, error);
            }
            if (root.has("detail")) {
                return new AgentClientException(404, "Agent 请求格式不符合协议：" + root.get("detail"), false, error);
            }
        } catch (Exception ignored) {
            // 非 JSON 响应使用 HTTP 状态兜底，仍然保留可重试属性。
        }
        int httpCode = error.getStatusCode().value();
        if (httpCode == 408 || httpCode == 504) {
            return new AgentClientException(401, "Agent 服务请求超时", true, error);
        }
        if (httpCode >= 500) {
            return new AgentClientException(400, "Agent 服务暂时不可用", true, error);
        }
        return new AgentClientException(402, "Agent 执行失败", false, error);
    }
}
