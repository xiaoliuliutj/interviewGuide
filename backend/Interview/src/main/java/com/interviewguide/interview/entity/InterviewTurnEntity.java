package com.interviewguide.interview.entity;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.Instant;

@TableName("interview_turn")
public class InterviewTurnEntity {
    @TableId
    private String id;
    private String sessionId;
    @TableField("turn_index")
    private int turnIndex;
    private String stage;
    private String question;
    private String answer;
    private String evaluationSummary;
    private Integer score;
    private Instant createdAt;

    /** 返回回合主键。 */
    public String getId() { return id; }
    /** 设置回合主键。 */
    public void setId(String id) { this.id = id; }
    /** 返回该回合关联的面试会话。 */
    public String getSessionId() { return sessionId; }
    /** 设置该回合关联的面试会话。 */
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    /** 返回会话内的递增回合序号。 */
    public int getTurnIndex() { return turnIndex; }
    /** 设置会话内的递增回合序号。 */
    public void setTurnIndex(int turnIndex) { this.turnIndex = turnIndex; }
    /** 返回回合所属面试阶段。 */
    public String getStage() { return stage; }
    /** 设置回合所属面试阶段。 */
    public void setStage(String stage) { this.stage = stage; }
    /** 返回已由 Agent 发出的题目。 */
    public String getQuestion() { return question; }
    /** 设置已由 Agent 发出的题目。 */
    public void setQuestion(String question) { this.question = question; }
    /** 返回用户提交的回答。 */
    public String getAnswer() { return answer; }
    /** 设置用户提交的回答。 */
    public void setAnswer(String answer) { this.answer = answer; }
    /** 返回该回答的简要评价。 */
    public String getEvaluationSummary() { return evaluationSummary; }
    /** 设置该回答的简要评价。 */
    public void setEvaluationSummary(String evaluationSummary) { this.evaluationSummary = evaluationSummary; }
    /** 返回该回答分数。 */
    public Integer getScore() { return score; }
    /** 设置该回答分数。 */
    public void setScore(Integer score) { this.score = score; }
    /** 返回回合创建时间。 */
    public Instant getCreatedAt() { return createdAt; }
    /** 设置回合创建时间。 */
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
