package com.interviewguide.knowledgebase.entity;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.Instant;

@TableName("knowledge_base")
public class KnowledgeBaseEntity {
    @TableId
    private Long id;

    @TableField("agent_knowledge_base_id")
    private String agentKnowledgeBaseId;
    @TableField("agent_document_id")
    private String agentDocumentId;
    @TableField("owner_user_id")
    private String ownerUserId;
    private String name;
    private String category;
    @TableField("file_name")
    private String fileName;
    @TableField("content_type")
    private String contentType;
    @TableField("source_url")
    private String sourceUrl;
    @TableField("source_title")
    private String sourceTitle;
    @TableField("source_fetched_at")
    private Instant sourceFetchedAt;
    @TableField("source_hash")
    private String sourceHash;
    @TableField("file_size")
    private Long fileSize;
    private String status;
    @TableField("vector_error")
    private String vectorError;
    @TableField("retry_count")
    private Integer retryCount;
    @TableField("next_retry_at")
    private Instant nextRetryAt;
    @TableField("created_at")
    private Instant createdAt;
    @TableField("updated_at")
    private Instant updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getAgentKnowledgeBaseId() { return agentKnowledgeBaseId; }
    public void setAgentKnowledgeBaseId(String value) { this.agentKnowledgeBaseId = value; }
    public String getAgentDocumentId() { return agentDocumentId; }
    public void setAgentDocumentId(String value) { this.agentDocumentId = value; }
    public String getOwnerUserId() { return ownerUserId; }
    public void setOwnerUserId(String value) { this.ownerUserId = value; }
    public String getName() { return name; }
    public void setName(String value) { this.name = value; }
    public String getCategory() { return category; }
    public void setCategory(String value) { this.category = value; }
    public String getFileName() { return fileName; }
    public void setFileName(String value) { this.fileName = value; }
    public String getContentType() { return contentType; }
    public void setContentType(String value) { this.contentType = value; }
    public String getSourceUrl() { return sourceUrl; }
    public void setSourceUrl(String value) { this.sourceUrl = value; }
    public String getSourceTitle() { return sourceTitle; }
    public void setSourceTitle(String value) { this.sourceTitle = value; }
    public Instant getSourceFetchedAt() { return sourceFetchedAt; }
    public void setSourceFetchedAt(Instant value) { this.sourceFetchedAt = value; }
    public String getSourceHash() { return sourceHash; }
    public void setSourceHash(String value) { this.sourceHash = value; }
    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long value) { this.fileSize = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { this.status = value; }
    public String getVectorError() { return vectorError; }
    public void setVectorError(String value) { this.vectorError = value; }
    public Integer getRetryCount() { return retryCount; }
    public void setRetryCount(Integer value) { this.retryCount = value; }
    public Instant getNextRetryAt() { return nextRetryAt; }
    public void setNextRetryAt(Instant value) { this.nextRetryAt = value; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { this.createdAt = value; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { this.updatedAt = value; }
}
