package com.interviewguide.knowledgebase.entity;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.Instant;

@TableName("knowledge_base_delete_outbox")
public class KnowledgeBaseDeleteOutboxEntity {
    @TableId
    private String eventId;
    private Long knowledgeBaseId;
    private String userId;
    private String runId;
    private String status;
    private Integer attemptCount;
    private Instant nextAttemptAt;
    private Instant claimedAt;

    public String getEventId() { return eventId; }
    public void setEventId(String value) { this.eventId = value; }
    public Long getKnowledgeBaseId() { return knowledgeBaseId; }
    public void setKnowledgeBaseId(Long value) { this.knowledgeBaseId = value; }
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
