package com.interviewguide.interview.service;

import java.util.List;
import java.util.Map;

public interface InterviewService {
    List<Map<String, Object>> listSessions(String userId);
    Map<String, Object> createSession(String userId, Map<String, Object> request);
    Map<String, Object> getSession(String userId, String sessionId);
    Map<String, Object> submitAnswer(String userId, String sessionId, Map<String, Object> request);
    Map<String, Object> getAgentStatus(String userId, String sessionId);
    void completeInterview(String userId, String sessionId);
    void pauseInterview(String userId, String sessionId);
    Map<String, Object> findUnfinishedSession(String userId, String resumeId);
    byte[] exportInterviewReport(String userId, String sessionId);
    void deleteInterview(String userId, String sessionId);
}
