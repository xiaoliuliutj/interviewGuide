package com.interviewguide.resume.service;

import java.util.List;
import java.util.Map;
import org.springframework.web.multipart.MultipartFile;

public interface ResumeService {
    Map<String, Object> uploadAndAnalyze(String userId, MultipartFile file, String targetRole);
    List<Map<String, Object>> listResumes(String userId);
    Map<String, Object> getResumeDetail(String userId, String resumeId);
    void reanalyze(String userId, String resumeId, String targetRole);
    byte[] exportAnalysisReport(String userId, String resumeId);
    byte[] downloadResume(String userId, String resumeId);
    void deleteResume(String userId, String resumeId);
}
