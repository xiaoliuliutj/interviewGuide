package com.interviewguide.agent.service;

import com.interviewguide.agent.client.AgentClientException;
import com.interviewguide.common.results.ApiResult;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 将 Agent 的标准错误码直接传递给前端，避免 Java 重新猜测 Python 的失败来源。 */
@RestControllerAdvice
public class AgentExceptionHandler {
    /** 返回 Agent 的中文说明、错误码和可重试标识，前端可按码展示具体提示。 */
    @ExceptionHandler(AgentServiceException.class)
    public ResponseEntity<ApiResult<Map<String, Object>>> handleAgentFailure(AgentServiceException error) {
        HttpStatus status = error.getAgentCode() == 400 || error.getAgentCode() == 401
                ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
        return ResponseEntity.status(status).body(new ApiResult<>(error.getAgentCode(), Map.of(
                "message", error.getMessage(),
                "retryable", error.isRetryable()
        )));
    }

    /** 网络层未收到 Agent 响应时统一归为可重试的服务不可用。 */
    @ExceptionHandler(AgentClientException.class)
    public ResponseEntity<ApiResult<Map<String, Object>>> handleAgentTransportFailure(AgentClientException error) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(new ApiResult<>(400, Map.of(
                "message", "Agent 服务暂时不可用",
                "retryable", true
        )));
    }
}
