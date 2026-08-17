package com.interviewguide.resume.entity;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.Instant;

/** 保存简历删除请求，保证 Agent 暂时不可用时任务不会丢失。 */
@TableName("resume_delete_outbox")
public class ResumeDeleteOutboxEntity {
    @TableId
    private String eventId;
    private String resumeId;
    private String userId;
    private String runId;
    private String status;
    private Integer attemptCount;
    private Instant nextAttemptAt;
    private Instant claimedAt;

    public String getEventId() { return eventId; }
    public void setEventId(String value) { this.eventId = value; }
    public String getResumeId() { return resumeId; }
    public void setResumeId(String value) { this.resumeId = value; }
    public String getUserId() { return userId; }
    public void setUserId(String value) { this.userId = value; }
    public String getRunId() { return runId; }
    public void setRunId(String value) { this.runId = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { this.status = value; }
    public Integer getAttemptCount() { return attemptCount; }
    public void setAttemptCount(Integer value) { this.attemptCount = value; }
    public Instant getNextAttemptAt() { return nextAttemptAt; }
    public void setNextAttemptAt(Instant value) { this.nextAttemptAt = value; }
    public Instant getClaimedAt() { return claimedAt; }
    public void setClaimedAt(Instant value) { this.claimedAt = value; }
}
