package com.interviewguide.knowledgebase.service;

import java.util.List;
import java.util.Map;
import org.springframework.web.multipart.MultipartFile;

public interface KnowledgeBaseService {
    Map<String, Object> uploadKnowledgeBase(String userId, MultipartFile file, String name, String category, Map<String, String> source);
    List<Map<String, Object>> listKnowledgeBases(String userId, String sortBy, String vectorStatus);
    byte[] downloadKnowledgeBase(String userId, Long id);
    void deleteKnowledgeBase(String userId, Long id);
    List<String> listCategories(String userId);
    List<Map<String, Object>> getByCategory(String userId, String category);
    void updateCategory(String userId, Long id, String category);
    List<Map<String, Object>> search(String userId, String keyword);
    Map<String, Object> getStatistics(String userId);
    void revectorize(String userId, Long id);
}
