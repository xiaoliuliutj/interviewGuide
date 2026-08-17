package com.interviewguide.interview.service;

/** 表示 Agent 已因超时关闭会话，Java 已完成本地删除，前端应返回面试入口而非继续提交。 */
public class InterviewSessionClosedException extends RuntimeException {
    /** 创建携带用户可理解原因的关闭异常。 */
    public InterviewSessionClosedException(String message) {
        super(message);
    }
}
