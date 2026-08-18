package com.interviewguide.resume.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.service.AgentCallService;
import com.interviewguide.agent.service.AgentPromptService;
import com.interviewguide.agent.service.AgentRequestFactory;
import com.interviewguide.resume.entity.ResumeAnalysisEntity;
import com.interviewguide.resume.entity.ResumeEntity;
import com.interviewguide.resume.mapper.ResumeAnalysisMapper;
import com.interviewguide.resume.mapper.ResumeMapper;
import com.interviewguide.resume.mapper.ResumeDeleteOutboxMapper;
import com.interviewguide.resume.entity.ResumeDeleteOutboxEntity;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.interviewguide.utils.pdf.PdfReportService;
import java.time.Instant;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import com.fasterxml.jackson.core.type.TypeReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** 维护简历展示数据，并将文件处理和模型分析委托给独立 Agent。 */
@Service
public class ResumeServiceImpl implements ResumeService {
    private final ResumeMapper resumeMapper;
    private final ResumeAnalysisMapper analysisMapper;
    private final AgentCallService agentCallService;
    private final AgentRequestFactory requestFactory;
    private final AgentPromptService promptService;
    private final ObjectMapper objectMapper;
    private final PdfReportService pdfReportService;
    private final ResumeDeleteOutboxMapper deleteOutboxMapper;
    private static final long DELETE_RETRY_INTERVAL_MILLIS = TimeUnit.MINUTES.toMillis(30);
    private static final int MAX_DELETE_RETRIES = 2;

    /** 注入 Java 持久化组件与通用 Agent 调用支持，不直接处理简历正文。 */
    public ResumeServiceImpl(ResumeMapper resumeMapper, ResumeAnalysisMapper analysisMapper, AgentCallService agentCallService,
                             AgentRequestFactory requestFactory, AgentPromptService promptService, ObjectMapper objectMapper,
                             PdfReportService pdfReportService, ResumeDeleteOutboxMapper deleteOutboxMapper) {
        this.resumeMapper = resumeMapper;
        this.analysisMapper = analysisMapper;
        this.agentCallService = agentCallService;
        this.requestFactory = requestFactory;
        this.promptService = promptService;
        this.objectMapper = objectMapper;
        this.pdfReportService = pdfReportService;
        this.deleteOutboxMapper = deleteOutboxMapper;
    }

    /** 创建本地展示记录后提交 Agent 异步任务，Agent 以 runId 保证上传幂等。 */
    @Override
    public Map<String, Object> uploadAndAnalyze(String userId, MultipartFile file, String targetRole) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传简历不能为空");
        }
        String resumeId = UUID.randomUUID().toString();
        String runId = UUID.randomUUID().toString();
        ResumeEntity resume = new ResumeEntity();
        resume.setId(resumeId);
        resume.setUserId(userId);
        resume.setFileName(file.getOriginalFilename() == null ? "resume" : file.getOriginalFilename());
        resume.setContentType(file.getContentType());
        resume.setFileSize(file.getSize());
        resume.setTargetRole(targetRole);
        resume.setStatus("PROCESSING");
        resume.setAgentRunId(runId);
        resume.setCreatedAt(Instant.now());
        resume.setUpdatedAt(Instant.now());
        resumeMapper.insert(resume);
        ResumeAnalysisEntity analysis = new ResumeAnalysisEntity();
        analysis.setId(UUID.randomUUID().toString());
        analysis.setResumeId(resumeId);
        analysis.setStatus("PROCESSING");
        analysis.setUpdatedAt(Instant.now());
        analysisMapper.insert(analysis);
        try {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("resumeId", resumeId);
            data.put("fileName", resume.getFileName());
            data.put("contentType", resume.getContentType());
            data.put("targetRole", targetRole);
            data.put("fileContent", Base64.getEncoder().encodeToString(file.getBytes()));
            data.put("contentEncoding", "base64");
            AgentOperationRequest request = requestFactory.create(userId, resumeId, runId, "capability", "resume.upload",
                    promptService.render("Resume/upload.txt", Map.of("targetRole", targetRole, "fileName", resume.getFileName())), data, 0);
            applyAgentStatus(resume, analysis, agentCallService.execute(request).data());
            resumeMapper.updateById(resume);
            analysisMapper.updateById(analysis);
            Map<String, Object> response = toView(resume, analysis);
            response.put("storage", Map.of("resumeId", resumeId));
            return response;
        } catch (Exception error) {
            resume.setStatus("FAILED");
            analysis.setStatus("FAILED");
            analysis.setErrorMessage(error.getMessage());
            resumeMapper.updateById(resume);
            analysisMapper.updateById(analysis);
            if (error instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new IllegalStateException("读取上传简历失败", error);
        }
    }

    /** 返回当前用户的简历列表，列表读取只依赖 Java 已保存的展示投影。 */
    @Override
    public List<Map<String, Object>> listResumes(String userId) {
        return resumeMapper.selectList(new LambdaQueryWrapper<ResumeEntity>().eq(ResumeEntity::getUserId, userId).orderByDesc(ResumeEntity::getUpdatedAt))
                .stream().map(resume -> toView(resume, loadAnalysis(resume.getId()))).toList();
    }

    /** 查询详情时向 Agent 对账进行中的任务，Agent 不可用时返回最近数据库状态。 */
    @Override
    public Map<String, Object> getResumeDetail(String userId, String resumeId) {
        ResumeEntity resume = requireOwnedResume(userId, resumeId);
        ResumeAnalysisEntity analysis = loadAnalysis(resumeId);
        if (analysis == null) {
            throw new IllegalStateException("简历分析记录不存在");
        }
        if (analysis != null && "PROCESSING".equals(analysis.getStatus())) {
            try {
                AgentOperationRequest request = requestFactory.create(userId, resumeId, resume.getAgentRunId(), "capability", "resume.status", "",
                        Map.of("resumeRunId", resume.getAgentRunId()), 0);
                applyAgentStatus(resume, analysis, agentCallService.execute(request).data());
                resumeMapper.updateById(resume);
                analysisMapper.updateById(analysis);
            } catch (RuntimeException ignored) {
                // 查询降级为 Java 已保存状态，避免 Agent 暂时不可用阻断历史查看。
            }
        }
        return toView(resume, analysis);
    }

    /** 请求 Agent 使用其保存的原文重新建立分析任务。 */
    @Override
    public void reanalyze(String userId, String resumeId, String targetRole) {
        ResumeEntity resume = requireOwnedResume(userId, resumeId);
        ResumeAnalysisEntity analysis = loadAnalysis(resumeId);
        String runId = UUID.randomUUID().toString();
        AgentOperationRequest request = requestFactory.create(userId, resumeId, runId, "capability", "resume.reanalyze",
                promptService.render("Resume/reanalyze.txt", Map.of("resumeId", resumeId, "targetRole", targetRole)),
                Map.of("resumeId", resumeId, "targetRole", targetRole), 0);
        applyAgentStatus(resume, analysis, agentCallService.execute(request).data());
        resume.setTargetRole(targetRole);
        resume.setAgentRunId(runId);
        resumeMapper.updateById(resume);
        analysisMapper.updateById(analysis);
    }

    /** 将 Java 保存的评估结果渲染为真实 PDF，避免再次调用 Agent 或伪造文件格式。 */
    @Override
    public byte[] exportAnalysisReport(String userId, String resumeId) {
        ResumeAnalysisEntity analysis = loadAnalysis(requireOwnedResume(userId, resumeId).getId());
        if (analysis == null || analysis.getEvaluationJson() == null) {
            throw new IllegalStateException("简历评估尚未完成，无法导出");
        }
        try {
            return pdfReportService.createReport(
                    "简历分析报告",
                    objectMapper.readValue(analysis.getEvaluationJson(), new TypeReference<Map<String, Object>>() { })
            );
        } catch (JsonProcessingException error) {
            throw new IllegalStateException("简历评估结果格式错误，无法导出", error);
        }
    }

    /** 从 Agent 下载原始文件，Java 仅完成跨 HTTP 的 Base64 转换。 */
    @Override
    public byte[] downloadResume(String userId, String resumeId) {
        AgentOperationRequest request = requestFactory.create(userId, resumeId, UUID.randomUUID().toString(), "capability", "resume.download", "",
                Map.of("resumeId", requireOwnedResume(userId, resumeId).getId()), 0);
        Map<String, Object> data = agentCallService.execute(request).data();
        if (data == null || !(data.get("content") instanceof String content)) {
            throw new IllegalStateException("Agent 未返回简历文件内容");
        }
        return Base64.getDecoder().decode(content);
    }

    /** 先让 Agent 删除原文和长期记忆，成功后删除 Java 的展示元数据。 */
    @Override
    @Transactional
    public void deleteResume(String userId, String resumeId) {
        ResumeEntity resume = requireOwnedResume(userId, resumeId);
        ResumeDeleteOutboxEntity activeEvent = deleteOutboxMapper.findActiveByResumeId(resumeId);
        if (activeEvent != null) {
            if ("FAILED".equals(activeEvent.getStatus())) {
                // 用户再次点击删除时立即重新投递，不必等待下一次半小时定时窗口。
                activeEvent.setStatus("PENDING");
                activeEvent.setAttemptCount(0);
                activeEvent.setNextAttemptAt(Instant.now());
                deleteOutboxMapper.updateById(activeEvent);
                resume.setStatus("DELETE_REQUESTED");
                resume.setUpdatedAt(Instant.now());
                resumeMapper.updateById(resume);
            }
            return;
        }
        resume.setStatus("DELETE_REQUESTED");
        resume.setUpdatedAt(Instant.now());
        resumeMapper.updateById(resume);
        ResumeDeleteOutboxEntity event = new ResumeDeleteOutboxEntity();
        event.setEventId(UUID.randomUUID().toString());
        event.setResumeId(resumeId);
        event.setUserId(userId);
        event.setRunId(UUID.randomUUID().toString());
        event.setStatus("PENDING");
        event.setAttemptCount(0);
        event.setNextAttemptAt(Instant.now());
        deleteOutboxMapper.insert(event);
    }

    /** 定时投递删除任务；Agent 成功后才删除 Java 投影，失败则保留任务等待下一次重试。 */
    @Scheduled(fixedDelay = 30_000L)
    public void processDeleteOutbox() {
        deleteOutboxMapper.selectList(Wrappers.<ResumeDeleteOutboxEntity>lambdaQuery()
                .and(query -> query
                        .and(item -> item.in(ResumeDeleteOutboxEntity::getStatus, List.of("PENDING", "FAILED"))
                                .le(ResumeDeleteOutboxEntity::getNextAttemptAt, Instant.now()))
                        .or(item -> item.eq(ResumeDeleteOutboxEntity::getStatus, "PROCESSING")
                                .lt(ResumeDeleteOutboxEntity::getClaimedAt, Instant.now().minusSeconds(300))))
                .lt(ResumeDeleteOutboxEntity::getAttemptCount, MAX_DELETE_RETRIES + 1))
                .forEach(this::deliverDeleteEvent);
    }

    private void deliverDeleteEvent(ResumeDeleteOutboxEntity event) {
        ResumeEntity resume = resumeMapper.selectById(event.getResumeId());
        if (resume == null) {
            event.setStatus("COMPLETED");
            deleteOutboxMapper.updateById(event);
            return;
        }
        if (deleteOutboxMapper.claim(event.getEventId()) != 1) {
            return;
        }
        try {
            AgentOperationRequest request = requestFactory.create(event.getUserId(), event.getResumeId(), event.getRunId(),
                    "capability", "resume.delete", "", Map.of("resumeId", event.getResumeId()), 0);
            agentCallService.execute(request);
            // 兼容已经创建但尚未执行数据库迁移的旧实例，先显式删除分析记录，避免外键阻止简历删除。
            analysisMapper.delete(new LambdaQueryWrapper<ResumeAnalysisEntity>()
                    .eq(ResumeAnalysisEntity::getResumeId, event.getResumeId()));
            resumeMapper.deleteById(event.getResumeId());
            event.setStatus("COMPLETED");
        } catch (RuntimeException error) {
            int attempt = event.getAttemptCount() + 1;
            event.setAttemptCount(attempt);
            event.setStatus("FAILED");
            event.setNextAttemptAt(Instant.now().plusMillis(DELETE_RETRY_INTERVAL_MILLIS));
            resume.setStatus("DELETE_FAILED");
            resume.setUpdatedAt(Instant.now());
            resumeMapper.updateById(resume);
        }
        deleteOutboxMapper.updateById(event);
    }

    /** 后台对账处理中简历，Agent 暂时不可用时不修改本地状态，避免误报失败。 */
    @Scheduled(fixedDelay = 5_000L)
    public void reconcileAnalysisStatuses() {
        resumeMapper.selectList(new LambdaQueryWrapper<ResumeEntity>().eq(ResumeEntity::getStatus, "PROCESSING"))
                .forEach(resume -> {
                    ResumeAnalysisEntity analysis = loadAnalysis(resume.getId());
                    if (analysis == null || !"PROCESSING".equals(analysis.getStatus())) return;
                    try {
                        AgentOperationRequest request = requestFactory.create(resume.getUserId(), resume.getId(), resume.getAgentRunId(),
                                "capability", "resume.status", "", Map.of("resumeRunId", resume.getAgentRunId()), 0);
                        applyAgentStatus(resume, analysis, agentCallService.execute(request).data());
                        resumeMapper.updateById(resume);
                        analysisMapper.updateById(analysis);
                    } catch (RuntimeException ignored) {
                        // 网络或 Agent 暂时不可用时保留 PROCESSING，等待下一轮对账。
                    }
                });
    }

    /** 将 Agent 返回的任务结果保存为 Java 可展示的最小投影。 */
    private void applyAgentStatus(ResumeEntity resume, ResumeAnalysisEntity analysis, Map<String, Object> data) {
        String status = data == null ? "PROCESSING" : String.valueOf(data.getOrDefault("status", "PROCESSING"));
        String localStatus = "COMPLETED".equals(status) ? "COMPLETED" : status.startsWith("FAILED") ? "FAILED" : "PROCESSING";
        resume.setStatus(localStatus);
        resume.setUpdatedAt(Instant.now());
        analysis.setStatus(localStatus);
        analysis.setUpdatedAt(Instant.now());
        if (data != null && data.get("evaluation") != null) {
            try {
                analysis.setEvaluationJson(objectMapper.writeValueAsString(data.get("evaluation")));
            } catch (JsonProcessingException error) {
                throw new IllegalStateException("Agent 评估结果无法保存", error);
            }
        }
        if (data != null && data.get("errorMessage") != null) analysis.setErrorMessage(String.valueOf(data.get("errorMessage")));
    }

    /** 读取单份简历的分析投影。 */
    private ResumeAnalysisEntity loadAnalysis(String resumeId) {
        return analysisMapper.selectOne(new LambdaQueryWrapper<ResumeAnalysisEntity>().eq(ResumeAnalysisEntity::getResumeId, resumeId));
    }

    /** 在 Service 层按 userId 查询，拒绝跨用户读取、下载、重分析和删除。 */
    private ResumeEntity requireOwnedResume(String userId, String resumeId) {
        ResumeEntity resume = resumeMapper.selectOne(new LambdaQueryWrapper<ResumeEntity>().eq(ResumeEntity::getId, resumeId).eq(ResumeEntity::getUserId, userId));
        if (resume == null) throw new IllegalArgumentException("简历不存在或不属于当前用户");
        return resume;
    }

    /** 输出前端需要的元数据、状态和评估，不泄露 Agent 原文或内部执行细节。 */
    private Map<String, Object> toView(ResumeEntity resume, ResumeAnalysisEntity analysis) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("resumeId", resume.getId());
        view.put("fileName", resume.getFileName());
        view.put("targetRole", resume.getTargetRole());
        view.put("status", resume.getStatus());
        view.put("createdAt", resume.getCreatedAt());
        view.put("updatedAt", resume.getUpdatedAt());
        if (analysis != null) {
            view.put("evaluation", analysis.getEvaluationJson());
            view.put("errorMessage", analysis.getErrorMessage());
        }
        return view;
    }
}
