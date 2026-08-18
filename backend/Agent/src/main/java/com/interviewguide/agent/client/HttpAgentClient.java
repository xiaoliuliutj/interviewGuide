package com.interviewguide.agent.client;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewguide.agent.dto.AgentHealthResponse;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Locale;

/**
 * 负责将统一 Agent 协议通过 HTTP/1.1 发送到独立 Agent 服务，并将 HTTP 响应还原为协议对象。
 *
 * <p>使用 JDK 原生客户端显式构造 JSON 字符串请求体，避免不同 Spring HTTP 实现对连接升级和请求体写入行为的差异。</p>
 */
public class HttpAgentClient implements AgentClient {
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(65);

    private final HttpClient httpClient;
    private final URI baseUri;
    private final ObjectMapper objectMapper;

    /**
     * 创建 Agent HTTP 客户端。
     *
     * <p>客户端固定为 HTTP/1.1；请求体由 ObjectMapper 序列化后作为 UTF-8 文本直接发送。</p>
     */
    public HttpAgentClient(URI baseUri, ObjectMapper objectMapper) {
        this.baseUri = baseUri;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    /** 查询 Agent 存活状态，并校验响应体可以被当前协议读取。 */
    @Override
    public AgentHealthResponse health() {
        try {
            HttpResponse<String> response = send(HttpRequest.newBuilder(resolve("/internal/v1/health"))
                    .timeout(REQUEST_TIMEOUT)
                    .header("Accept", "application/json")
                    .GET()
                    .build());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw createHttpException(response.statusCode(), response.body());
            }
            return objectMapper.readValue(response.body(), AgentHealthResponse.class);
        } catch (JsonProcessingException error) {
            throw new AgentClientException(402, "Agent 健康检查响应格式错误", false, error);
        } catch (IOException error) {
            throw createTransportException(error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new AgentClientException(401, "Agent 健康检查被中断", true, error);
        }
    }

    /** 发送一次会话或 capability 请求，并保留 Agent 返回的完整协议状态。 */
    @Override
    public AgentOperationResponse execute(AgentOperationRequest request) {
        try {
            String requestJson = objectMapper.writeValueAsString(request);
            String path = "capability".equals(request.mode()) ? "/internal/v1/capabilities" : "/internal/v1/runs";
            HttpRequest httpRequest = HttpRequest.newBuilder(resolve(path))
                    .timeout(REQUEST_TIMEOUT)
                    .header("Content-Type", "application/json; charset=UTF-8")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestJson))
                    .build();
            HttpResponse<String> response = send(httpRequest);
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw createHttpException(response.statusCode(), response.body());
            }
            return objectMapper.readValue(response.body(), AgentOperationResponse.class);
        } catch (JsonProcessingException error) {
            throw new AgentClientException(402, "Agent 请求或响应序列化失败", false, error);
        } catch (IOException error) {
            throw createTransportException(error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new AgentClientException(401, "Agent 请求被中断", true, error);
        }
    }

    /** 执行 HTTP 请求，集中保留网络异常的原始原因，供上层重试和熔断策略判断。 */
    private HttpResponse<String> send(HttpRequest request) throws IOException, InterruptedException {
        return httpClient.send(request, HttpResponse.BodyHandlers.ofString());
    }

    /** 将网络不可达、连接超时和读取超时转换为可重试的 Agent 通信错误。 */
    private AgentClientException createTransportException(IOException error) {
        String detail = error.getMessage() == null ? "" : error.getMessage().toLowerCase(Locale.ROOT);
        if (detail.contains("timed out") || detail.contains("timeout")) {
            return new AgentClientException(401, "Agent 服务请求超时", true, error);
        }
        return new AgentClientException(400, "Agent 服务暂时不可用", true, error);
    }

    /** 解析 Agent 的标准失败响应；协议校验失败和非 JSON 响应均保留为可定位的中文状态。 */
    private AgentClientException createHttpException(int httpCode, String body) {
        try {
            JsonNode root = objectMapper.readTree(body);
            if (root.has("statusCode")) {
                int code = root.path("statusCode").asInt(400);
                JsonNode agentError = root.path("error");
                String message = agentError.path("message").asText("Agent 执行失败");
                return new AgentClientException(code, message, agentError.path("retryable").asBoolean(false));
            }
            if (root.has("detail")) {
                return new AgentClientException(404, "Agent 请求格式不符合协议：" + root.path("detail"), false);
            }
        } catch (Exception ignored) {
            // 非 JSON 响应按 HTTP 状态统一转换，避免丢失调用失败原因。
        }
        if (httpCode == 408 || httpCode == 504) {
            return new AgentClientException(401, "Agent 服务请求超时", true);
        }
        if (httpCode >= 500) {
            return new AgentClientException(400, "Agent 服务暂时不可用", true);
        }
        return new AgentClientException(402, "Agent 执行失败", false);
    }

    /** 以基础地址解析接口路径，支持配置地址末尾带或不带斜杠。 */
    private URI resolve(String path) {
        return baseUri.resolve(path.startsWith("/") ? path.substring(1) : path);
    }
}
