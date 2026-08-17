package com.interviewguide.knowledgebase.controller;

import com.interviewguide.common.results.ApiResult;
import com.interviewguide.knowledgebase.service.WebService;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tools/web")
public class WebController {
    private final WebService webService;

    public WebController(WebService webService) {
        this.webService = webService;
    }

    /** 代理单网页读取能力，供前端展示用户将要导入的原始网页正文。 */
    @PostMapping("/fetch")
    public ApiResult<Map<String, Object>> fetchWebPage(
            @RequestHeader("X-User-Id") String userId,
            @RequestBody Map<String, Object> request
    ) {
        return ApiResult.success(webService.fetchWebPage(userId, request));
    }

    /** 创建同域深度抓取预览，结果中的令牌后续由导入和归档接口使用。 */
    @PostMapping("/crawl")
    public ApiResult<Map<String, Object>> crawlWebSite(
            @RequestHeader("X-User-Id") String userId,
            @RequestBody Map<String, Object> request
    ) {
        return ApiResult.success(webService.crawlWebSite(userId, request));
    }

    /** 将预览中用户选中的多个网页提交为独立的异步知识库索引任务。 */
    @PostMapping("/crawl/import")
    public ApiResult<Map<String, Object>> importWebCrawl(
            @RequestHeader("X-User-Id") String userId,
            @RequestBody Map<String, Object> request
    ) {
        return ApiResult.success(webService.importWebCrawl(userId, request));
    }

    /** 下载 Agent 侧持久化的网页抓取 Markdown 归档。 */
    @GetMapping("/crawl/{previewToken}/archive")
    public ResponseEntity<byte[]> downloadWebCrawlArchive(
            @RequestHeader("X-User-Id") String userId,
            @PathVariable String previewToken
    ) {
        return ResponseEntity.ok(webService.downloadWebCrawlArchive(userId, previewToken));
    }
}
