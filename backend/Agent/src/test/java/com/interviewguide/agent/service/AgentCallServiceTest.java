package com.interviewguide.agent.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.interviewguide.agent.client.AgentClient;
import com.interviewguide.agent.client.AgentClientException;
import com.interviewguide.agent.dto.AgentError;
import com.interviewguide.agent.dto.AgentHealthResponse;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import com.interviewguide.agent.dto.AgentRequestContext;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/** 验证 Java 侧 Agent 调用的重试、错误码传递与幂等运行标识不被执行器修改。 */
class AgentCallServiceTest {
    /** 网络暂时失败后应复用原请求重试，并返回同一 runId 的成功响应。 */
    @Test
    void shouldRetryTransportFailureWithSameRequest() {
        AtomicInteger attempts = new AtomicInteger();
        AgentClient client = new AgentClient() {
            @Override
            public AgentHealthResponse health() {
                return new AgentHealthResponse("UP");
            }

            @Override
            public AgentOperationResponse execute(AgentOperationRequest request) {
                if (attempts.incrementAndGet() == 1) {
                    throw new AgentClientException("网络暂时不可用");
                }
                return successResponse(request);
            }
        };
        AgentOperationRequest request = request();
        AgentOperationResponse response = new AgentCallService(client, new AgentResponseGuard()).execute(request);
        assertEquals(2, attempts.get());
        assertEquals(request.context().runId(), response.runId());
    }

    /** Agent 的不可重试业务失败应原样携带错误码抛给 Java Service，而不是盲目重试。 */
    @Test
    void shouldExposeNonRetryableAgentFailure() {
        AgentClient client = new AgentClient() {
            @Override
            public AgentHealthResponse health() {
                return new AgentHealthResponse("UP");
            }

            @Override
            public AgentOperationResponse execute(AgentOperationRequest request) {
                return new AgentOperationResponse(
                        "v1", request.context().requestId(), request.context().runId(),
                        request.context().principalId(), request.context().conversationId(),
                        422, "FAILED", 0, null,
                        new AgentError("ToolArgumentError", "工具调用参数不合法", false), Instant.now()
                );
            }
        };
        AgentServiceException error = assertThrows(
                AgentServiceException.class,
                () -> new AgentCallService(client, new AgentResponseGuard()).execute(request())
        );
        assertEquals(422, error.getAgentCode());
        assertEquals("工具调用参数不合法", error.getMessage());
    }

    /** 连续不可用后应直接熔断，业务 Service 可以据此返回本地缓存或处理中状态。 */
    @Test
    void shouldOpenCircuitAfterRepeatedUnavailableFailures() {
        AtomicInteger attempts = new AtomicInteger();
        AgentClient client = new AgentClient() {
            @Override
            public AgentHealthResponse health() {
                return new AgentHealthResponse("UP");
            }

            @Override
            public AgentOperationResponse execute(AgentOperationRequest request) {
                attempts.incrementAndGet();
                throw new AgentClientException("网络暂时不可用");
            }
        };
        AgentCallService service = new AgentCallService(client, new AgentResponseGuard());
        assertThrows(AgentServiceException.class, () -> service.execute(request()));
        assertThrows(AgentServiceException.class, () -> service.execute(request()));
        assertThrows(AgentServiceException.class, () -> service.execute(request()));
        int attemptsBeforeCircuit = attempts.get();
        AgentServiceException error = assertThrows(AgentServiceException.class, () -> service.execute(request()));
        assertEquals(attemptsBeforeCircuit, attempts.get());
        assertEquals("Agent 服务暂时熔断，请稍后重试", error.getMessage());
    }

    /** 创建最小通用请求，模拟业务 Service 已构造好的跨层协议。 */
    private AgentOperationRequest request() {
        return new AgentOperationRequest(
                new AgentRequestContext("v1", "request-1", "run-1", "user-1", "session-1", Instant.now()),
                "conversation", null, "测试提示词", Map.of(), 0
        );
    }

    /** 创建与请求关联信息完全一致的成功响应。 */
    private AgentOperationResponse successResponse(AgentOperationRequest request) {
        return new AgentOperationResponse(
                "v1", request.context().requestId(), request.context().runId(),
                request.context().principalId(), request.context().conversationId(),
                100, "COMPLETED", 0, Map.of("result", "ok"), null, Instant.now()
        );
    }
}
