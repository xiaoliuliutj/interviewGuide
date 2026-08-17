package com.interviewguide.resume.controller;

import com.interviewguide.common.results.ApiResult;
import com.interviewguide.resume.service.ResumeService;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/resumes")
public class ResumeController {
    private final ResumeService resumeService;

    public ResumeController(ResumeService resumeService) {
        this.resumeService = resumeService;
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResult<Map<String, Object>> uploadAndAnalyze(@RequestHeader("X-User-Id") String userId, @RequestParam MultipartFile file, @RequestParam String targetRole) { return ApiResult.success(resumeService.uploadAndAnalyze(userId, file, targetRole)); }
    @GetMapping public ApiResult<List<Map<String, Object>>> listResumes(@RequestHeader("X-User-Id") String userId) { return ApiResult.success(resumeService.listResumes(userId)); }
    @GetMapping("/{resumeId}/detail") public ApiResult<Map<String, Object>> getResumeDetail(@RequestHeader("X-User-Id") String userId, @PathVariable String resumeId) { return ApiResult.success(resumeService.getResumeDetail(userId, resumeId)); }
    @PostMapping("/{resumeId}/reanalyze") public ApiResult<Void> reanalyze(@RequestHeader("X-User-Id") String userId, @PathVariable String resumeId, @RequestParam String targetRole) { resumeService.reanalyze(userId, resumeId, targetRole); return ApiResult.successWithoutData(); }
    @GetMapping(value = "/{resumeId}/export", produces = MediaType.APPLICATION_PDF_VALUE) public ResponseEntity<byte[]> exportAnalysisReport(@RequestHeader("X-User-Id") String userId, @PathVariable String resumeId) { return ResponseEntity.ok(resumeService.exportAnalysisReport(userId, resumeId)); }
    @GetMapping("/{resumeId}/download") public ResponseEntity<byte[]> downloadResume(@RequestHeader("X-User-Id") String userId, @PathVariable String resumeId) { return ResponseEntity.ok(resumeService.downloadResume(userId, resumeId)); }
    @DeleteMapping("/{resumeId}") public ApiResult<Void> deleteResume(@RequestHeader("X-User-Id") String userId, @PathVariable String resumeId) { resumeService.deleteResume(userId, resumeId); return ApiResult.successWithoutData(); }
}
