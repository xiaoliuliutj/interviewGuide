package com.interviewguide.interview.controller;

import com.interviewguide.common.results.ApiResult;
import com.interviewguide.interview.service.InterviewService;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/interviews")
public class InterviewController {
    private final InterviewService interviewService;

    public InterviewController(InterviewService interviewService) {
        this.interviewService = interviewService;
    }

    @GetMapping public ApiResult<List<Map<String, Object>>> listSessions(@RequestHeader("X-User-Id") String userId) { return ApiResult.success(interviewService.listSessions(userId)); }
    @PostMapping public ApiResult<Map<String, Object>> createSession(@RequestHeader("X-User-Id") String userId, @RequestBody Map<String, Object> request) { return ApiResult.success(interviewService.createSession(userId, request)); }
    @GetMapping("/{sessionId}") public ApiResult<Map<String, Object>> getSession(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId) { return ApiResult.success(interviewService.getSession(userId, sessionId)); }
    @PostMapping("/{sessionId}/answers") public ApiResult<Map<String, Object>> submitAnswer(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId, @RequestBody Map<String, Object> request) { return ApiResult.success(interviewService.submitAnswer(userId, sessionId, request)); }
    @GetMapping("/{sessionId}/agent-status") public ApiResult<Map<String, Object>> getAgentStatus(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId) { return ApiResult.success(interviewService.getAgentStatus(userId, sessionId)); }
    @PostMapping("/{sessionId}/complete") public ApiResult<Void> completeInterview(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId) { interviewService.completeInterview(userId, sessionId); return ApiResult.successWithoutData(); }
    @PostMapping("/{sessionId}/pause") public ApiResult<Void> pauseInterview(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId) { interviewService.pauseInterview(userId, sessionId); return ApiResult.successWithoutData(); }
    @GetMapping("/unfinished/{resumeId}")
    public ApiResult<Map<String, Object>> findUnfinishedSession(
            @RequestHeader("X-User-Id") String userId,
            @PathVariable String resumeId
    ) {
        Map<String, Object> session = interviewService.findUnfinishedSession(userId, resumeId);
        return session == null ? ApiResult.successWithoutData() : ApiResult.success(session);
    }

    @GetMapping("/unfinished")
    public ApiResult<Map<String, Object>> findAnyUnfinishedSession(
            @RequestHeader("X-User-Id") String userId
    ) {
        Map<String, Object> session = interviewService.findUnfinishedSession(userId, null);
        return session == null ? ApiResult.successWithoutData() : ApiResult.success(session);
    }
    @GetMapping(value = "/{sessionId}/export", produces = MediaType.APPLICATION_PDF_VALUE) public ResponseEntity<byte[]> exportInterviewReport(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId) { return ResponseEntity.ok(interviewService.exportInterviewReport(userId, sessionId)); }
    @DeleteMapping("/{sessionId}") public ApiResult<Void> deleteInterview(@RequestHeader("X-User-Id") String userId, @PathVariable String sessionId) { interviewService.deleteInterview(userId, sessionId); return ApiResult.successWithoutData(); }
}
