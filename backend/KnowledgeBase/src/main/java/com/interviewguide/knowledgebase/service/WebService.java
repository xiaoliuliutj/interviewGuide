package com.interviewguide.knowledgebase.service;

import java.util.Map;

public interface WebService {
    Map<String, Object> fetchWebPage(String userId, Map<String, Object> request);
    Map<String, Object> crawlWebSite(String userId, Map<String, Object> request);
    Map<String, Object> importWebCrawl(String userId, Map<String, Object> request);
    byte[] downloadWebCrawlArchive(String userId, String previewToken);
}
