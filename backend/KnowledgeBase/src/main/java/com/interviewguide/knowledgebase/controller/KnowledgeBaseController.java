package com.interviewguide.knowledgebase.controller;

import com.interviewguide.common.results.ApiResult;
import com.interviewguide.knowledgebase.service.KnowledgeBaseService;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/knowledgebase")
public class KnowledgeBaseController {
    private final KnowledgeBaseService knowledgeBaseService;

    public KnowledgeBaseController(KnowledgeBaseService knowledgeBaseService) {
        this.knowledgeBaseService = knowledgeBaseService;
    }

    @PostMapping("/upload") public ApiResult<Map<String, Object>> uploadKnowledgeBase(@RequestHeader("X-User-Id") String userId, @RequestParam MultipartFile file, @RequestParam(required = false) String name, @RequestParam(required = false) String category, @RequestParam Map<String, String> source) { return ApiResult.success(knowledgeBaseService.uploadKnowledgeBase(userId, file, name, category, source)); }
    @GetMapping("/list") public ApiResult<List<Map<String, Object>>> listKnowledgeBases(@RequestHeader("X-User-Id") String userId, @RequestParam(required = false) String sortBy, @RequestParam(required = false) String vectorStatus) { return ApiResult.success(knowledgeBaseService.listKnowledgeBases(userId, sortBy, vectorStatus)); }
    @GetMapping("/{id}/download") public ResponseEntity<byte[]> downloadKnowledgeBase(@RequestHeader("X-User-Id") String userId, @PathVariable Long id) { return ResponseEntity.ok(knowledgeBaseService.downloadKnowledgeBase(userId, id)); }
    @DeleteMapping("/{id}") public ApiResult<Void> deleteKnowledgeBase(@RequestHeader("X-User-Id") String userId, @PathVariable Long id) { knowledgeBaseService.deleteKnowledgeBase(userId, id); return ApiResult.successWithoutData(); }
    @GetMapping("/categories") public ApiResult<List<String>> listCategories(@RequestHeader("X-User-Id") String userId) { return ApiResult.success(knowledgeBaseService.listCategories(userId)); }
    @GetMapping("/category/{category}") public ApiResult<List<Map<String, Object>>> getByCategory(@RequestHeader("X-User-Id") String userId, @PathVariable String category) { return ApiResult.success(knowledgeBaseService.getByCategory(userId, category)); }
    @PutMapping("/{id}/category") public ApiResult<Void> updateCategory(@RequestHeader("X-User-Id") String userId, @PathVariable Long id, @RequestBody Map<String, String> request) { knowledgeBaseService.updateCategory(userId, id, request.get("category")); return ApiResult.successWithoutData(); }
    @GetMapping("/search") public ApiResult<List<Map<String, Object>>> search(@RequestHeader("X-User-Id") String userId, @RequestParam String keyword) { return ApiResult.success(knowledgeBaseService.search(userId, keyword)); }
    @GetMapping("/stats") public ApiResult<Map<String, Object>> getStatistics(@RequestHeader("X-User-Id") String userId) { return ApiResult.success(knowledgeBaseService.getStatistics(userId)); }
    @PostMapping("/{id}/revectorize") public ApiResult<Void> revectorize(@RequestHeader("X-User-Id") String userId, @PathVariable Long id) { knowledgeBaseService.revectorize(userId, id); return ApiResult.successWithoutData(); }
}
