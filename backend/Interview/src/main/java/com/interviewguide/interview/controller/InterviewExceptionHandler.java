package com.interviewguide.interview.controller;

import com.interviewguide.common.results.ApiResult;
import com.interviewguide.common.results.ResultStatus;
import com.interviewguide.interview.service.InterviewSessionClosedException;
import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 将面试业务异常转换为统一 ApiResult，避免前端收到 Spring 默认错误页面。 */
@RestControllerAdvice(basePackageClasses = InterviewController.class)
public class InterviewExceptionHandler {
    /** 处理六小时超时后自动删除的会话，前端据此返回面试入口。 */
    @ExceptionHandler(InterviewSessionClosedException.class)
    public ResponseEntity<ApiResult<Map<String, String>>> handleClosedSession(
            InterviewSessionClosedException error
    ) {
        return ResponseEntity.status(HttpStatus.GONE).body(
                ApiResult.failure(
                        ResultStatus.JAVA_RESOURCE_NOT_FOUND,
                        Map.of("message", error.getMessage(), "reason", "INTERVIEW_CLOSED")
                )
        );
    }

    /** 处理可预期的参数或会话状态错误，保持前端统一按业务状态码解析。 */
    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    public ResponseEntity<ApiResult<Map<String, String>>> handleBusinessError(RuntimeException error) {
        ResultStatus status = error instanceof IllegalArgumentException
                ? ResultStatus.INVALID_PARAMETER
                : ResultStatus.JAVA_BUSINESS_ERROR;
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                ApiResult.failure(status, Map.of("message", error.getMessage()))
        );
    }

    /** 处理数据库唯一约束拒绝的并发创建，向前端返回可恢复的业务提示而不是通用五百错误。 */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiResult<Map<String, String>>> handleConcurrentCreation(
            DataIntegrityViolationException error
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                ApiResult.failure(
                        ResultStatus.JAVA_BUSINESS_ERROR,
                        Map.of("message", "当前用户存在未完成面试，请先继续、结束或关闭后再创建新的面试")
                )
        );
    }

    /** 处理 Agent 网络故障等未分类异常，仍保持统一结果结构而不泄露堆栈信息。 */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResult<Map<String, String>>> handleUnexpectedError(Exception error) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(
                ApiResult.failure(
                        ResultStatus.JAVA_INTERNAL_ERROR,
                        Map.of("message", "面试服务暂时无法处理请求")
                )
        );
    }
}
