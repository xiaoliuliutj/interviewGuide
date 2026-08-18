package com.interviewguide.agent.service;

import com.interviewguide.agent.client.AgentClientException;
import com.interviewguide.common.results.ApiResult;
import com.interviewguide.common.results.ResultStatus;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 将 Agent 的完整状态码、中文说明和重试属性统一返回给前端。 */
@RestControllerAdvice
public class AgentExceptionHandler {
    /** 保留 Agent 原始状态码，同时补充统一目录说明和具体错误消息。 */
    @ExceptionHandler(AgentServiceException.class)
    public ResponseEntity<ApiResult<Map<String, Object>>> handleAgentFailure(AgentServiceException error) {
        HttpStatus status = error.getAgentCode() == 400 || error.getAgentCode() == 401
                ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
        return ResponseEntity.status(status).body(new ApiResult<>(error.getAgentCode(), createErrorData(
                error.getAgentCode(), error.getMessage(), error.isRetryable())));
    }

    /** 网络层未收到 Agent 响应时，返回统一的可重试状态。 */
    @ExceptionHandler(AgentClientException.class)
    public ResponseEntity<ApiResult<Map<String, Object>>> handleAgentTransportFailure(AgentClientException error) {
        int code = error.getAgentCode();
        HttpStatus status = code == 400 || code == 401
                ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
        return ResponseEntity.status(status).body(new ApiResult<>(code,
                createErrorData(code, error.getMessage(), error.isRetryable())));
    }

    /** 组装前端需要的状态码、标准说明、具体消息和重试标志。 */
    private Map<String, Object> createErrorData(int code, String message, boolean retryable) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("statusCode", code);
        data.put("statusMessage", ResultStatus.descriptionOf(code));
        data.put("message", message == null || message.isBlank() ? ResultStatus.descriptionOf(code) : message);
        data.put("retryable", retryable);
        return data;
    }
}
