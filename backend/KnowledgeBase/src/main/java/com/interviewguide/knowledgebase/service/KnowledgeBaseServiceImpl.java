package com.interviewguide.knowledgebase.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import com.interviewguide.agent.dto.AgentRequestContext;
import com.interviewguide.agent.service.AgentCallService;
import com.interviewguide.agent.service.AgentServiceException;
import com.interviewguide.knowledgebase.entity.KnowledgeBaseEntity;
import com.interviewguide.knowledgebase.entity.KnowledgeBaseDeleteOutboxEntity;
import com.interviewguide.knowledgebase.mapper.KnowledgeBaseDeleteOutboxMapper;
import com.interviewguide.knowledgebase.mapper.KnowledgeBaseMapper;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class KnowledgeBaseServiceImpl implements KnowledgeBaseService {
    private static final String READY = "READY";
    private static final String BUILDING = "BUILDING";
    private static final String DELETE_REQUESTED = "DELETE_REQUESTED";
    private static final String DELETE_FAILED = "DELETE_FAILED";
    private static final String DELETED = "DELETED";
    private static final long RETRY_INTERVAL_MILLIS = TimeUnit.MINUTES.toMillis(30);
    private static final int MAX_DELETE_RETRIES = 2;
    private static final long MAX_DOCUMENT_BYTES = 20L * 1024L * 1024L;

    private final KnowledgeBaseMapper mapper;
    private final KnowledgeBaseDeleteOutboxMapper deleteOutboxMapper;
    private final AgentCallService agentCallService;

    public KnowledgeBaseServiceImpl(
            KnowledgeBaseMapper mapper,
            KnowledgeBaseDeleteOutboxMapper deleteOutboxMapper,
            AgentCallService agentCallService
    ) {
        this.mapper = mapper;
        this.deleteOutboxMapper = deleteOutboxMapper;
        this.agentCallService = agentCallService;
    }

    /** 创建 Java 元数据后调用 Agent 完成文件解析和向量入库，成功后才切换 READY。 */
    @Override
    public Map<String, Object> uploadKnowledgeBase(String userId, MultipartFile file, String name, String category, Map<String, String> source) {
        requireUser(userId);
        requireFile(file);
        requireDocumentSize(file);
        KnowledgeBaseEntity entity = new KnowledgeBaseEntity();
        entity.setAgentKnowledgeBaseId(UUID.randomUUID().toString());
        entity.setAgentDocumentId(UUID.randomUUID().toString());
        entity.setOwnerUserId(userId);
        entity.setName(name == null || name.isBlank() ? file.getOriginalFilename() : name);
        entity.setCategory(category);
        entity.setFileName(file.getOriginalFilename() == null ? "document" : file.getOriginalFilename());
        entity.setContentType(file.getContentType());
        if (source != null) {
            entity.setSourceUrl(source.getOrDefault("url", source.get("sourceUrl")));
            entity.setSourceTitle(source.getOrDefault("title", source.get("sourceTitle")));
            entity.setSourceHash(source.getOrDefault("contentHash", source.get("sourceHash")));
            String fetchedAt = source.getOrDefault("fetchedAt", source.get("sourceFetchedAt"));
            if (fetchedAt != null) {
                entity.setSourceFetchedAt(OffsetDateTime.parse(fetchedAt).toInstant());
            }
        }
        entity.setFileSize(file.getSize());
        entity.setStatus(BUILDING);
        entity.setRetryCount(0);
        mapper.insert(entity);
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("knowledgeBaseId", entity.getAgentKnowledgeBaseId());
            payload.put("documentId", entity.getAgentDocumentId());
            payload.put("fileName", entity.getFileName());
            payload.put("contentType", entity.getContentType());
            payload.put("documentContent", Base64.getEncoder().encodeToString(file.getBytes()));
            payload.put("contentEncoding", "base64");
            agentCallService.execute(createRequest(userId, "knowledge_base.index", payload));
            entity.setStatus(BUILDING);
            mapper.updateById(entity);
        } catch (AgentServiceException error) {
            entity.setStatus("INDEX_FAILED");
            mapper.updateById(entity);
            throw error;
        } catch (Exception error) {
            entity.setStatus("INDEX_FAILED");
            mapper.updateById(entity);
            throw new IllegalStateException("知识库索引构建失败", error);
        }
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("knowledgeBase", toView(entity));
        return response;
    }

    /** 按用户隔离元数据，并只返回前端可展示的状态与标签。 */
    @Override
    public List<Map<String, Object>> listKnowledgeBases(String userId, String sortBy, String vectorStatus) {
        requireUser(userId);
        List<Map<String, Object>> result = new ArrayList<>();
        for (KnowledgeBaseEntity entity : mapper.selectByOwner(userId)) {
            if (DELETED.equals(entity.getStatus())) {
                continue;
            }
            if (vectorStatus == null || vectorStatus.isBlank() || vectorStatus.equals(toFrontendStatus(entity.getStatus()))) {
                result.add(toView(entity));
            }
        }
        return result;
    }

    /** 通过 Agent 读取原始文件，Java 只负责校验归属和转换传输结果。 */
    @Override
    public byte[] downloadKnowledgeBase(String userId, Long id) {
        KnowledgeBaseEntity entity = requireOwned(userId, id);
        Map<String, Object> payload = Map.of(
                "knowledgeBaseId", entity.getAgentKnowledgeBaseId(),
                "documentId", entity.getAgentDocumentId()
        );
        AgentOperationResponse response = agentCallService.execute(
                createRequest(userId, "knowledge_base.download", payload)
        );
        Object encoded = response.data() == null ? null : response.data().get("content");
        if (!(encoded instanceof String value)) {
            throw new IllegalStateException("Agent 下载响应缺少文件内容");
        }
        return Base64.getDecoder().decode(value);
    }

    /** 先立即标记不可用，再调用 Agent 删除；失败进入半小时后的自动重试状态。 */
    @Override
    @Transactional
    public void deleteKnowledgeBase(String userId, Long id) {
        KnowledgeBaseEntity entity = requireOwned(userId, id);
        if (DELETED.equals(entity.getStatus())) {
            return;
        }
        KnowledgeBaseDeleteOutboxEntity existingEvent = deleteOutboxMapper.findActiveByKnowledgeBaseId(entity.getId());
        if (existingEvent != null) {
            if ("FAILED".equals(existingEvent.getStatus())
                    && existingEvent.getAttemptCount() >= MAX_DELETE_RETRIES + 1) {
                existingEvent.setStatus("PENDING");
                existingEvent.setAttemptCount(0);
                existingEvent.setNextAttemptAt(Instant.now());
                deleteOutboxMapper.updateById(existingEvent);
                entity.setStatus(DELETE_REQUESTED);
                mapper.updateById(entity);
            }
            return;
        }
        entity.setStatus(DELETE_REQUESTED);
        mapper.updateById(entity);
        KnowledgeBaseDeleteOutboxEntity event = new KnowledgeBaseDeleteOutboxEntity();
        event.setEventId(UUID.randomUUID().toString());
        event.setKnowledgeBaseId(entity.getId());
        event.setUserId(userId);
        event.setRunId(UUID.randomUUID().toString());
        event.setStatus("PENDING");
        event.setAttemptCount(0);
        event.setNextAttemptAt(Instant.now());
        deleteOutboxMapper.insert(event);
    }

    @Override
    public List<String> listCategories(String userId) {
        requireUser(userId);
        return mapper.selectByOwner(userId).stream().map(KnowledgeBaseEntity::getCategory)
                .filter(value -> value != null && !value.isBlank()).distinct().toList();
    }

    @Override
    public List<Map<String, Object>> getByCategory(String userId, String category) {
        return listKnowledgeBases(userId, null, null).stream()
                .filter(item -> category == null || category.equals(item.get("category"))).toList();
    }

    @Override
    public void updateCategory(String userId, Long id, String category) {
        KnowledgeBaseEntity entity = requireOwned(userId, id);
        entity.setCategory(category);
        mapper.updateById(entity);
    }

    @Override
    public List<Map<String, Object>> search(String userId, String keyword) {
        return listKnowledgeBases(userId, null, null).stream()
                .filter(item -> keyword == null || keyword.isBlank() || String.valueOf(item.get("name")).contains(keyword)).toList();
    }

    @Override
    public Map<String, Object> getStatistics(String userId) {
        List<Map<String, Object>> items = listKnowledgeBases(userId, null, null);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", items.size());
        result.put("totalCount", items.size());
        result.put("ready", items.stream().filter(item -> READY.equals(item.get("status"))).count());
        result.put("completedCount", items.stream().filter(item -> "COMPLETED".equals(item.get("vectorStatus"))).count());
        result.put("processingCount", items.stream().filter(item -> "PROCESSING".equals(item.get("vectorStatus"))).count());
        result.put("failedCount", items.stream().filter(item -> "FAILED".equals(item.get("vectorStatus")) || "DELETE_FAILED".equals(item.get("vectorStatus"))).count());
        result.put("deleting", items.stream().filter(item -> DELETE_REQUESTED.equals(item.get("status")) || DELETE_FAILED.equals(item.get("status"))).count());
        return result;
    }

    @Override
    public void revectorize(String userId, Long id) {
        KnowledgeBaseEntity entity = requireOwned(userId, id);
        Map<String, Object> downloadPayload = Map.of(
                "knowledgeBaseId", entity.getAgentKnowledgeBaseId(),
                "documentId", entity.getAgentDocumentId()
        );
        AgentOperationResponse download = agentCallService.execute(
                createRequest(userId, "knowledge_base.download", downloadPayload)
        );
        if (download.data() == null || !(download.data().get("content") instanceof String content)) {
            throw new AgentServiceException(444, "Agent 未保存知识库原文件，请重新上传知识库", false);
        }
        entity.setStatus(BUILDING);
        mapper.updateById(entity);
        Map<String, Object> indexPayload = new LinkedHashMap<>();
        indexPayload.put("knowledgeBaseId", entity.getAgentKnowledgeBaseId());
        indexPayload.put("documentId", entity.getAgentDocumentId());
        indexPayload.put("fileName", entity.getFileName());
        indexPayload.put("contentType", entity.getContentType());
        indexPayload.put("documentContent", content);
        indexPayload.put("contentEncoding", "base64");
        try {
            agentCallService.execute(
                    createRequest(userId, "knowledge_base.index", indexPayload)
            );
            entity.setStatus(BUILDING);
            mapper.updateById(entity);
        } catch (AgentServiceException error) {
            entity.setStatus("INDEX_FAILED");
            mapper.updateById(entity);
            throw error;
        } catch (Exception error) {
            entity.setStatus("INDEX_FAILED");
            mapper.updateById(entity);
            throw new IllegalStateException("重新向量化失败", error);
        }
    }

    /** 定时领取到期删除任务，最多自动重试两次。 */
    @Scheduled(fixedDelay = 30_000L)
    public void processDeleteOutbox() {
        deleteOutboxMapper.selectList(Wrappers.<KnowledgeBaseDeleteOutboxEntity>lambdaQuery()
                .and(wrapper -> wrapper
                        .and(item -> item.in(KnowledgeBaseDeleteOutboxEntity::getStatus, List.of("PENDING", "FAILED"))
                                .le(KnowledgeBaseDeleteOutboxEntity::getNextAttemptAt, Instant.now()))
                        .or(item -> item.eq(KnowledgeBaseDeleteOutboxEntity::getStatus, "PROCESSING")
                                .lt(KnowledgeBaseDeleteOutboxEntity::getClaimedAt, Instant.now().minusSeconds(300))))
                .lt(KnowledgeBaseDeleteOutboxEntity::getAttemptCount, MAX_DELETE_RETRIES + 1))
                .forEach(this::deliverDeleteEvent);
    }

    @Scheduled(fixedDelay = 5_000L)
    public void reconcileIndexStatuses() {
        mapper.selectList(Wrappers.<KnowledgeBaseEntity>lambdaQuery()
                .in(KnowledgeBaseEntity::getStatus, List.of(BUILDING, "INDEX_FAILED")))
                .forEach(this::reconcileIndexStatus);
    }

    private void reconcileIndexStatus(KnowledgeBaseEntity entity) {
        try {
            AgentOperationResponse response = agentCallService.execute(createRequest(
                    entity.getOwnerUserId(),
                    "knowledge_base.index_status",
                    Map.of("knowledgeBaseId", entity.getAgentKnowledgeBaseId())
            ));
            String status = response.data() == null ? null : String.valueOf(response.data().get("status"));
            if (READY.equals(status)) {
                entity.setStatus(READY);
                mapper.updateById(entity);
            } else if ("FAILED".equals(status)) {
                entity.setStatus("INDEX_FAILED");
                Object errorMessage = response.data().get("errorMessage");
                entity.setVectorError(errorMessage == null ? "Agent 知识库索引失败" : String.valueOf(errorMessage));
                mapper.updateById(entity);
            }
        } catch (Exception ignored) {
            // Agent 暂不可用时保留 BUILDING，下一次调度继续对账。
        }
    }

    /** 使用同一知识库 ID 调 Agent，保证重复删除请求幂等。 */
    private void deliverDeleteEvent(KnowledgeBaseDeleteOutboxEntity event) {
        KnowledgeBaseEntity entity = mapper.selectById(event.getKnowledgeBaseId());
        if (entity == null || DELETED.equals(entity.getStatus())) {
            event.setStatus("COMPLETED");
            deleteOutboxMapper.updateById(event);
            return;
        }
        if (deleteOutboxMapper.claim(event.getEventId()) != 1) {
            return;
        }
        event.setStatus("PROCESSING");
        try {
            agentCallService.execute(createRequest(entity.getOwnerUserId(), "knowledge_base.delete", Map.of("knowledgeBaseId", entity.getAgentKnowledgeBaseId()), event.getRunId()));
            entity.setStatus(DELETED);
            entity.setNextRetryAt(null);
            event.setStatus("COMPLETED");
        } catch (Exception error) {
            int attempt = event.getAttemptCount() + 1;
            event.setAttemptCount(attempt);
            event.setStatus("FAILED");
            event.setNextAttemptAt(Instant.now().plusMillis(RETRY_INTERVAL_MILLIS));
            entity.setRetryCount(attempt);
            entity.setStatus(DELETE_FAILED);
            entity.setNextRetryAt(Instant.now().plusMillis(RETRY_INTERVAL_MILLIS));
        }
        mapper.updateById(entity);
        deleteOutboxMapper.updateById(event);
    }

    private AgentOperationRequest createRequest(String userId, String capability, Map<String, Object> payload) {
        return createRequest(userId, capability, payload, UUID.randomUUID().toString());
    }

    private AgentOperationRequest createRequest(String userId, String capability, Map<String, Object> payload, String runId) {
        String requestId = UUID.randomUUID().toString();
        AgentRequestContext context = new AgentRequestContext("v1", requestId, runId, userId, requestId, Instant.now());
        return new AgentOperationRequest(context, "capability", capability, "", payload, 0);
    }

    private KnowledgeBaseEntity requireOwned(String userId, Long id) {
        requireUser(userId);
        KnowledgeBaseEntity entity = mapper.selectById(id);
        if (entity == null || !userId.equals(entity.getOwnerUserId())) {
            throw new IllegalArgumentException("知识库不存在或无权访问");
        }
        return entity;
    }

    private void requireUser(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("用户标识不能为空");
        }
    }

    private void requireFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传文件不能为空");
        }
    }

    /** 校验文件大小，避免超大文件在 Agent 队列中占用无界资源。 */
    private void requireDocumentSize(MultipartFile file) {
        if (file.getSize() > MAX_DOCUMENT_BYTES) {
            throw new IllegalArgumentException("文件超过允许的大小限制");
        }
    }

    private Map<String, Object> toView(KnowledgeBaseEntity entity) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", entity.getId());
        result.put("name", entity.getName());
        result.put("category", entity.getCategory());
        result.put("fileName", entity.getFileName());
        result.put("originalFilename", entity.getFileName());
        result.put("fileSize", entity.getFileSize());
        result.put("status", entity.getStatus());
        result.put("vectorStatus", toFrontendStatus(entity.getStatus()));
        result.put("vectorError", entity.getVectorError());
        result.put("contentType", entity.getContentType());
        result.put("sourceUrl", entity.getSourceUrl());
        result.put("sourceTitle", entity.getSourceTitle());
        result.put("sourceFetchedAt", entity.getSourceFetchedAt());
        result.put("sourceHash", entity.getSourceHash());
        result.put("uploadedAt", entity.getCreatedAt());
        result.put("updatedAt", entity.getUpdatedAt());
        result.put("retryCount", entity.getRetryCount());
        result.put("nextRetryAt", entity.getNextRetryAt());
        result.put("statusMessage", statusMessage(entity));
        return result;
    }

    /** 将内部状态映射为前端契约，避免把 Agent 的生命周期枚举泄漏给页面。 */
    private String toFrontendStatus(String status) {
        return switch (status) {
            case READY -> "COMPLETED";
            case BUILDING -> "PROCESSING";
            case DELETE_REQUESTED -> "DELETING";
            case DELETE_FAILED -> "DELETE_FAILED";
            case DELETED -> "DELETED";
            default -> "FAILED";
        };
    }

    /** 生成删除状态的固定前端文案，重试次数只由 Java 状态机决定。 */
    private String statusMessage(KnowledgeBaseEntity entity) {
        if (DELETE_FAILED.equals(entity.getStatus())) {
            int retryCount = entity.getRetryCount() == null ? 0 : entity.getRetryCount();
            return retryCount <= MAX_DELETE_RETRIES
                    ? "删除失败，等待重试（" + retryCount + "/2）"
                    : "删除失败，请手动重试";
        }
        if (DELETE_REQUESTED.equals(entity.getStatus())) {
            return "删除失败，重试中";
        }
        return null;
    }
}
