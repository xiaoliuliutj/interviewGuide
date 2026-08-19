package com.interviewguide.knowledgebase.service;

import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import com.interviewguide.agent.dto.AgentRequestContext;
import com.interviewguide.agent.service.AgentCallService;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.interviewguide.knowledgebase.entity.KnowledgeBaseEntity;
import com.interviewguide.knowledgebase.mapper.KnowledgeBaseMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WebServiceImpl implements WebService {
    private static final String BUILDING = "BUILDING";

    private final AgentCallService agentCallService;
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    /**
     * 注入 Agent 的稳定通信边界和知识库元数据仓储。
     * 网页正文、抓取预览与向量数据均由 Agent 保存，Java 只保存展示所需元数据。
     */
    public WebServiceImpl(AgentCallService agentCallService, KnowledgeBaseMapper knowledgeBaseMapper) {
        this.agentCallService = agentCallService;
        this.knowledgeBaseMapper = knowledgeBaseMapper;
    }

    /**
     * 读取一个公开网页以供用户导入前预览。
     * Java 不实现抓取、重定向与 SSRF 防护，而是调用 Agent 的网页读取能力。
     */
    @Override
    public Map<String, Object> fetchWebPage(String userId, Map<String, Object> request) {
        return requireData(agentCallService.execute(createRequest(userId, "web.fetch", request)));
    }

    /**
     * 创建持久化的同域深度抓取预览。
     * Agent 返回的 previewToken 用于后续页面选择、批量导入和原始 Markdown 归档下载。
     */
    @Override
    public Map<String, Object> crawlWebSite(String userId, Map<String, Object> request) {
        return requireData(agentCallService.execute(
                createRequest(userId, "knowledge_base.url_crawl", request)
        ));
    }

    /**
     * 将选中的网页逐页创建为独立知识库，并在本地事务中写入对应展示元数据。
     * Agent 负责正文保存、自动切分和异步索引，Java 不复制网页正文内容。
     */
    @Override
    @Transactional
    public Map<String, Object> importWebCrawl(String userId, Map<String, Object> request) {
        String importRunId = createWebImportRunId(userId, request);
        Map<String, Object> agentData = requireData(agentCallService.execute(
                createRequest(userId, "knowledge_base.url_import", request, importRunId)
        ));
        Object rawKnowledgeBases = agentData.get("knowledgeBases");
        if (!(rawKnowledgeBases instanceof List<?> items)) {
            throw new IllegalStateException("Agent 网页导入响应缺少知识库列表");
        }

        String category = request.get("category") instanceof String value ? value : null;
        List<Map<String, Object>> knowledgeBases = new ArrayList<>();
        for (Object item : items) {
            if (!(item instanceof Map<?, ?> rawPage)) {
                throw new IllegalStateException("Agent 网页导入响应包含无效页面");
            }
            Map<String, Object> page = new LinkedHashMap<>();
            rawPage.forEach((key, value) -> page.put(String.valueOf(key), value));
            String agentKnowledgeBaseId = requireString(page, "knowledgeBaseId");
            KnowledgeBaseEntity entity = knowledgeBaseMapper.selectOne(
                    Wrappers.<KnowledgeBaseEntity>lambdaQuery()
                            .eq(KnowledgeBaseEntity::getAgentKnowledgeBaseId, agentKnowledgeBaseId)
            );
            if (entity == null) {
                entity = createWebKnowledgeBase(userId, category, page);
                knowledgeBaseMapper.insert(entity);
            }
            knowledgeBases.add(toView(entity));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("importRunId", agentData.get("importRunId"));
        result.put("importedCount", knowledgeBases.size());
        result.put("knowledgeBases", knowledgeBases);
        return result;
    }

    /**
     * 下载 Agent 持久化保存的网页 Markdown 归档。
     * Agent 用 Base64 完成跨服务传输，Java 仅完成 HTTP 下载响应需要的字节转换。
     */
    @Override
    public byte[] downloadWebCrawlArchive(String userId, String previewToken) {
        Map<String, Object> data = requireData(agentCallService.execute(
                createRequest(userId, "knowledge_base.url_archive", Map.of("previewToken", previewToken))
        ));
        Object content = data.get("content");
        if (!(content instanceof String encoded)) {
            throw new IllegalStateException("Agent 网页归档响应缺少文件内容");
        }
        return Base64.getDecoder().decode(encoded);
    }

    /**
     * 将 Agent 页面结果转换为 Java 知识库元数据。
     * 每页使用独立知识库 ID，因此单页重建或删除不会影响同批次的其他页面。
     */
    private KnowledgeBaseEntity createWebKnowledgeBase(
            String userId,
            String category,
            Map<String, Object> page
    ) {
        String title = requireString(page, "title");
        KnowledgeBaseEntity entity = new KnowledgeBaseEntity();
        entity.setAgentKnowledgeBaseId(requireString(page, "knowledgeBaseId"));
        entity.setAgentDocumentId(requireString(page, "documentId"));
        entity.setOwnerUserId(userId);
        entity.setName(title);
        entity.setCategory(category);
        entity.setFileName(requireString(page, "fileName"));
        entity.setContentType("text/markdown");
        entity.setSourceUrl(requireString(page, "url"));
        entity.setSourceTitle(title);
        entity.setSourceHash(requireString(page, "contentHash"));
        entity.setSourceFetchedAt(Instant.now());
        entity.setFileSize(((Number) page.getOrDefault("characterCount", 0)).longValue());
        entity.setStatus(BUILDING);
        entity.setRetryCount(0);
        return entity;
    }

    /**
     * 构造不依赖 Java 内部会话模型的通用 Agent capability 请求。
     * 此处的 conversationId 仅用作跨服务关联标识，并不要求 Agent 理解 Java 的业务会话规则。
     */
    private AgentOperationRequest createRequest(
            String userId,
            String capability,
            Map<String, Object> data
    ) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("用户标识不能为空");
        }
        String requestId = UUID.randomUUID().toString();
        AgentRequestContext context = new AgentRequestContext(
                "v1",
                requestId,
                UUID.randomUUID().toString(),
                userId,
                requestId,
                Instant.now()
        );
        return new AgentOperationRequest(context, "capability", capability, "", data, 0);
    }

    /**
     * 为同一预览与同一组页面生成稳定的导入运行标识。
     * 网络超时或前端重复提交会重放同一 Agent 导入批次，而不是再次建立重复知识库。
     */
    private String createWebImportRunId(String userId, Map<String, Object> request) {
        Object rawPreviewToken = request.get("previewToken");
        Object rawPageIds = request.get("selectedPageIds");
        if (!(rawPreviewToken instanceof String previewToken) || previewToken.isBlank()
                || !(rawPageIds instanceof List<?> pageIds) || pageIds.isEmpty()) {
            throw new IllegalArgumentException("网页导入需要预览令牌和至少一个页面标识");
        }
        List<String> sortedPageIds = pageIds.stream()
                .map(String::valueOf)
                .sorted()
                .toList();
        String seed = userId + "|" + previewToken + "|" + String.join(",", sortedPageIds);
        return UUID.nameUUIDFromBytes(seed.getBytes(StandardCharsets.UTF_8)).toString();
    }

    /**
     * 使用调用方指定的稳定运行标识创建 capability 请求。
     * 该重载仅用于需要跨 HTTP 重试幂等重放的网页批量导入场景。
     */
    private AgentOperationRequest createRequest(
            String userId,
            String capability,
            Map<String, Object> data,
            String runId
    ) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("用户标识不能为空");
        }
        String requestId = UUID.randomUUID().toString();
        AgentRequestContext context = new AgentRequestContext(
                "v1",
                requestId,
                runId,
                userId,
                requestId,
                Instant.now()
        );
        return new AgentOperationRequest(context, "capability", capability, "", data, 0);
    }

    /**
     * 校验 Agent 统一响应并提取非空 data。
     * Agent 的错误信息被保留在异常中，便于 Java 的全局异常处理层转换为对前端的业务响应。
     */
    private Map<String, Object> requireData(AgentOperationResponse response) {
        if (response == null || (response.statusCode() != 100 && response.statusCode() != 101)) {
            throw new IllegalStateException(
                    response == null ? "Agent 未返回响应" : "Agent 操作失败: " + response.error()
            );
        }
        if (response.data() == null) {
            throw new IllegalStateException("Agent 响应缺少结果数据");
        }
        return response.data();
    }



    /**
     * 获取 Agent 返回的必要文本字段，确保下载、删除和异步状态对账可以关联同一知识库。
     */
    private String requireString(Map<String, Object> page, String field) {
        Object value = page.get(field);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalStateException("Agent 网页导入响应缺少 " + field);
        }
        return text;
    }

    /**
     * 输出网页批量导入后前端立即可展示的最小状态字段。
     * 后续索引完成状态继续由既有的知识库状态对账任务更新。
     */
    private Map<String, Object> toView(KnowledgeBaseEntity entity) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", entity.getId());
        result.put("name", entity.getName());
        result.put("filename", entity.getFileName());
        result.put("fileName", entity.getFileName());
        result.put("vectorStatus", "PROCESSING");
        result.put("status", entity.getStatus());
        return result;
    }
}
