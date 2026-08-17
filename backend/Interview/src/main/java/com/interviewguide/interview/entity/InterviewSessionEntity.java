package com.interviewguide.interview.entity;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.Instant;

@TableName("interview_session")
public class InterviewSessionEntity {
    @TableId
    private String sessionId;
    private String userId;
    private String resumeId;
    private String targetRole;
    private String interviewDirection;
    private String difficulty;
    private String status;
    private long stateVersion;
    private String currentQuestion;
    private String currentStage;
    private String currentTopic;
    private int issuedQuestionCount;
    private int primaryQuestionCount;
    private int totalPrimaryQuestionCount;
    private int followupCount;
    private int totalQuestions;
    @TableField("final_evaluation_json")
    private String finalEvaluationJson;
    private Instant createdAt;
    private Instant updatedAt;

    /** 返回会话标识，供 Controller 与 Agent 关联同一场面试。 */
    public String getSessionId() { return sessionId; }
    /** 设置会话标识，Java 负责在创建会话时生成并持久化该值。 */
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    /** 返回当前会话的调用主体标识。 */
    public String getUserId() { return userId; }
    /** 设置会话所属用户，查询时始终与该字段一起限定。 */
    public void setUserId(String userId) { this.userId = userId; }
    /** 返回本场面试使用的简历标识。 */
    public String getResumeId() { return resumeId; }
    /** 设置面试关联的简历标识。 */
    public void setResumeId(String resumeId) { this.resumeId = resumeId; }
    /** 返回目标岗位。 */
    public String getTargetRole() { return targetRole; }
    /** 设置目标岗位。 */
    public void setTargetRole(String targetRole) { this.targetRole = targetRole; }
    /** 返回前端选择的面试方向。 */
    public String getInterviewDirection() { return interviewDirection; }
    /** 设置前端选择的面试方向。 */
    public void setInterviewDirection(String interviewDirection) { this.interviewDirection = interviewDirection; }
    /** 返回面试难度。 */
    public String getDifficulty() { return difficulty; }
    /** 设置面试难度。 */
    public void setDifficulty(String difficulty) { this.difficulty = difficulty; }
    /** 返回会话生命周期状态。 */
    public String getStatus() { return status; }
    /** 设置会话生命周期状态。 */
    public void setStatus(String status) { this.status = status; }
    /** 返回 Agent 权威状态的乐观锁版本。 */
    public long getStateVersion() { return stateVersion; }
    /** 设置 Agent 返回的最新状态版本。 */
    public void setStateVersion(long stateVersion) { this.stateVersion = stateVersion; }
    /** 返回待回答问题。 */
    public String getCurrentQuestion() { return currentQuestion; }
    /** 设置待回答问题。 */
    public void setCurrentQuestion(String currentQuestion) { this.currentQuestion = currentQuestion; }
    /** 返回当前面试阶段。 */
    public String getCurrentStage() { return currentStage; }
    /** 设置当前面试阶段。 */
    public void setCurrentStage(String currentStage) { this.currentStage = currentStage; }
    /** 返回当前主题。 */
    public String getCurrentTopic() { return currentTopic; }
    /** 设置当前主题。 */
    public void setCurrentTopic(String currentTopic) { this.currentTopic = currentTopic; }
    /** 返回累计已发出问题数。 */
    public int getIssuedQuestionCount() { return issuedQuestionCount; }
    /** 设置累计已发出问题数。 */
    public void setIssuedQuestionCount(int issuedQuestionCount) { this.issuedQuestionCount = issuedQuestionCount; }
    /** 返回当前阶段主问题计数。 */
    public int getPrimaryQuestionCount() { return primaryQuestionCount; }
    /** 设置当前阶段主问题计数。 */
    public void setPrimaryQuestionCount(int primaryQuestionCount) { this.primaryQuestionCount = primaryQuestionCount; }
    /** 返回累计主问题计数。 */
    public int getTotalPrimaryQuestionCount() { return totalPrimaryQuestionCount; }
    /** 设置累计主问题计数。 */
    public void setTotalPrimaryQuestionCount(int totalPrimaryQuestionCount) { this.totalPrimaryQuestionCount = totalPrimaryQuestionCount; }
    /** 返回当前问题追问次数。 */
    public int getFollowupCount() { return followupCount; }
    /** 设置当前问题追问次数。 */
    public void setFollowupCount(int followupCount) { this.followupCount = followupCount; }
    /** 返回动态问题上限。 */
    public int getTotalQuestions() { return totalQuestions; }
    /** 设置动态问题上限。 */
    public void setTotalQuestions(int totalQuestions) { this.totalQuestions = totalQuestions; }
    /** 返回序列化后的最终评价。 */
    public String getFinalEvaluationJson() { return finalEvaluationJson; }
    /** 设置序列化后的最终评价。 */
    public void setFinalEvaluationJson(String finalEvaluationJson) { this.finalEvaluationJson = finalEvaluationJson; }
    /** 返回创建时间。 */
    public Instant getCreatedAt() { return createdAt; }
    /** 设置创建时间。 */
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    /** 返回最后推进时间，六小时自动关闭以该字段为依据。 */
    public Instant getUpdatedAt() { return updatedAt; }
    /** 设置最后推进时间。 */
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
