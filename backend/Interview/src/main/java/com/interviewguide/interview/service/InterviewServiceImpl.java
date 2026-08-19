package com.interviewguide.interview.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;
import com.interviewguide.agent.dto.AgentRequestContext;
import com.interviewguide.agent.service.AgentCallService;
import com.interviewguide.agent.service.AgentPromptService;
import com.interviewguide.interview.entity.InterviewSessionEntity;
import com.interviewguide.interview.entity.InterviewTurnEntity;
import com.interviewguide.interview.entity.InterviewCloseOutboxEntity;
import com.interviewguide.interview.mapper.InterviewCloseOutboxMapper;
import com.interviewguide.interview.mapper.InterviewSessionMapper;
import com.interviewguide.interview.mapper.InterviewTurnMapper;
import com.interviewguide.utils.pdf.PdfReportService;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 负责面试公开接口的持久化、Agent 调用和前端展示数据组装。 */
@Service
public class InterviewServiceImpl implements InterviewService {
    private static final long INACTIVITY_SECONDS = 6 * 60 * 60;

    private final InterviewSessionMapper interviewSessionMapper;
    private final InterviewTurnMapper interviewTurnMapper;
    private final AgentCallService agentCallService;
    private final ObjectMapper objectMapper;
    private final AgentPromptService promptService;
    private final PdfReportService pdfReportService;
    private final InterviewCloseOutboxMapper closeOutboxMapper;
    private static final long CLOSE_RETRY_INTERVAL_MILLIS = TimeUnit.MINUTES.toMillis(30);
    private static final int MAX_CLOSE_RETRIES = 2;

    /** 注入 Java 侧面试持久化组件和独立 Agent 客户端。 */
    public InterviewServiceImpl(
            InterviewSessionMapper interviewSessionMapper,
            InterviewTurnMapper interviewTurnMapper,
            AgentCallService agentCallService,
            ObjectMapper objectMapper,
            AgentPromptService promptService,
            PdfReportService pdfReportService,
            InterviewCloseOutboxMapper closeOutboxMapper
    ) {
        this.interviewSessionMapper = interviewSessionMapper;
        this.interviewTurnMapper = interviewTurnMapper;
        this.agentCallService = agentCallService;
        this.objectMapper = objectMapper;
        this.promptService = promptService;
        this.pdfReportService = pdfReportService;
        this.closeOutboxMapper = closeOutboxMapper;
    }

    /** 查询用户自己的面试列表，前端据此识别是否存在未完成会话。 */
    @Override
    public List<Map<String, Object>> listSessions(String userId) {
        return interviewSessionMapper.selectList(
                        new LambdaQueryWrapper<InterviewSessionEntity>()
                                .eq(InterviewSessionEntity::getUserId, userId)
                                .orderByDesc(InterviewSessionEntity::getCreatedAt)
                ).stream()
                .map(this::toSessionView)
                .toList();
    }

    /** 创建 Java 展示记录，调用 Agent 生成第一道题后才正式保存为可继续状态。 */
    @Override
    public Map<String, Object> createSession(String userId, Map<String, Object> request) {
        if (findUnfinishedEntity(userId) != null) {
            throw new IllegalStateException("当前用户存在未完成面试，请先结束或关闭后再开始新的面试");
        }
        String sessionId = UUID.randomUUID().toString();
        Object resumeIdValue = request.get("resumeId");
        Object targetRoleValue = request.get("targetRole");
        if (!(resumeIdValue instanceof String resumeId) || resumeId.isBlank()
                || !(targetRoleValue instanceof String targetRole) || targetRole.isBlank()) {
            throw new IllegalArgumentException("缺少简历或目标岗位信息");
        }
        resumeId = resumeId.trim();
        targetRole = targetRole.trim();
        Object difficultyValue = request.get("desiredDifficulty");
        String difficulty = difficultyValue instanceof String value && !value.isBlank()
                ? value.trim() : "MEDIUM";
        InterviewSessionEntity entity = new InterviewSessionEntity();
        entity.setSessionId(sessionId);
        entity.setUserId(userId);
        entity.setResumeId(resumeId);
        entity.setTargetRole(targetRole);
        Object directionValue = request.get("interviewDirection");
        entity.setInterviewDirection(directionValue instanceof String value && !value.isBlank() ? value.trim() : null);
        entity.setDifficulty(difficulty);
        // 先持久化创建保留状态，使 PostgreSQL 的部分唯一索引能够原子阻止并发创建第二场未完成面试。
        entity.setStatus("CREATING");
        entity.setCreatedAt(Instant.now());
        entity.setUpdatedAt(Instant.now());
        interviewSessionMapper.insert(entity);
        Map<String, Object> data = new LinkedHashMap<>(request);
        data.put("resumeId", resumeId);
        data.put("targetRole", targetRole);
        AgentOperationRequest agentRequest = createRequest(
                userId, sessionId, UUID.randomUUID().toString(), promptService.render("Interview/start.txt", Map.of(
                        "resumeId", resumeId,
                        "targetRole", targetRole,
                        "difficulty", difficulty,
                        "interviewDirection", String.valueOf(entity.getInterviewDirection())
                )),
                data, 0, "conversation", null
        );
        try {
            AgentOperationResponse agentResponse = agentCallService.execute(agentRequest);
            entity.setStatus("ACTIVE");
            entity.setUpdatedAt(Instant.now());
            applyAgentData(entity, agentResponse.data());
            entity.setStateVersion(agentResponse.stateVersion());
            interviewSessionMapper.updateById(entity);
            return toSessionView(entity);
        } catch (RuntimeException error) {
            // 远程调用的结果可能因网络中断而未知，因此即使本地没有收到成功响应也尽力关闭同一会话。
            requestSessionClosure(entity);
            throw error;
        }
    }

    /** 查询用户拥有的会话及其回答回合。 */
    @Override
    public Map<String, Object> getSession(String userId, String sessionId) {
        InterviewSessionEntity entity = requireOwnedSession(userId, sessionId);
        return toDetailView(entity);
    }

    /** 将用户回答提交给 Agent，并把 Agent 返回的状态和上一道题的回答落到 Java 数据库。 */
    @Override
    @Transactional(noRollbackFor = InterviewSessionClosedException.class)
    public Map<String, Object> submitAnswer(String userId, String sessionId, Map<String, Object> request) {
        InterviewSessionEntity entity = requireOwnedSession(userId, sessionId);
        if (!"ACTIVE".equals(entity.getStatus()) && !"PAUSED".equals(entity.getStatus())) {
            throw new IllegalStateException("当前面试不允许继续回答");
        }
        Object answerValue = request.get("answer");
        if (!(answerValue instanceof String answer) || answer.isBlank()) {
            throw new IllegalArgumentException("缺少回答内容");
        }
        answer = answer.trim();
        Object runIdValue = request.get("runId");
        String runId = runIdValue instanceof String value && !value.isBlank()
                ? value.trim() : UUID.randomUUID().toString();
        AgentOperationRequest agentRequest = createRequest(
                userId, sessionId, runId, promptService.render("Interview/answer.txt", Map.of("answer", answer)),
                Map.of("resumeId", entity.getResumeId()), entity.getStateVersion(), "conversation", null
        );
        AgentOperationResponse agentResponse = agentCallService.execute(agentRequest);
        Map<String, Object> data = agentResponse.data() == null ? Map.of() : agentResponse.data();
        if ("INTERVIEW_CLOSED".equals(data.get("type"))) {
            deleteLocalSession(sessionId);
            throw new InterviewSessionClosedException("面试已因超过六小时未推进而自动关闭");
        }
        saveAnswerTurn(entity, answer, data);
        applyAgentData(entity, data);
        entity.setStateVersion(agentResponse.stateVersion());
        entity.setUpdatedAt(Instant.now());
        interviewSessionMapper.updateById(entity);
        return toDetailView(entity);
    }

    /** 返回 Java 当前保存的阶段信息，前端只需要展示，不参与 Agent 状态推进。 */
    @Override
    public Map<String, Object> getAgentStatus(String userId, String sessionId) {
        InterviewSessionEntity entity = requireOwnedSession(userId, sessionId);
        return Map.of(
                "stage", entity.getCurrentStage() == null ? "IDLE" : entity.getCurrentStage(),
                "status", entity.getStatus(),
                "stateVersion", entity.getStateVersion()
        );
    }

    /** 正常完成面试，必须让 Agent 生成最终评价后再更新 Java 状态。 */
    @Override
    @Transactional(noRollbackFor = InterviewSessionClosedException.class)
    public void completeInterview(String userId, String sessionId) {
        InterviewSessionEntity entity = requireOwnedSession(userId, sessionId);
        if ("COMPLETED".equals(entity.getStatus())) {
            return;
        }
        AgentOperationRequest request = createRequest(
                userId, sessionId, UUID.randomUUID().toString(), promptService.render("Interview/complete.txt", Map.of()),
                Map.of(), entity.getStateVersion(), "capability", "interview.complete"
        );
        AgentOperationResponse response = agentCallService.execute(request);
        if (response.data() != null && "INTERVIEW_CLOSED".equals(response.data().get("type"))) {
            deleteLocalSession(sessionId);
            throw new InterviewSessionClosedException("面试已因超过六小时未推进而自动关闭");
        }
        applyAgentData(entity, response.data());
        entity.setStatus("COMPLETED");
        entity.setStateVersion(response.stateVersion());
        entity.setUpdatedAt(Instant.now());
        interviewSessionMapper.updateById(entity);
    }

    /** 暂停一个面试会话；暂停不会生成评价，也不会删除历史。 */
    @Override
    @Transactional
    public void pauseInterview(String userId, String sessionId) {
        InterviewSessionEntity entity = requireOwnedSession(userId, sessionId);
        if (!"ACTIVE".equals(entity.getStatus())) {
            return;
        }
        AgentOperationRequest request = createRequest(
                userId, sessionId, UUID.randomUUID().toString(), promptService.render("Interview/pause.txt", Map.of()),
                Map.of(), entity.getStateVersion(), "capability", "interview.pause"
        );
        AgentOperationResponse response = agentCallService.execute(request);
        applyAgentData(entity, response.data());
        entity.setStatus("PAUSED");
        entity.setStateVersion(response.stateVersion());
        entity.setUpdatedAt(Instant.now());
        interviewSessionMapper.updateById(entity);
    }

    /** 查找用户指定简历下的未完成会话，兼容旧前端入口。 */
    @Override
    public Map<String, Object> findUnfinishedSession(String userId, String resumeId) {
        LambdaQueryWrapper<InterviewSessionEntity> query = new LambdaQueryWrapper<InterviewSessionEntity>()
                .eq(InterviewSessionEntity::getUserId, userId)
                // CREATING 同样占用用户的唯一未完成面试名额，其他页面必须等待创建请求结束。
                .in(InterviewSessionEntity::getStatus, List.of("CREATING", "ACTIVE", "PAUSED"))
                .orderByDesc(InterviewSessionEntity::getUpdatedAt)
                .last("LIMIT 1");
        if (resumeId != null && !resumeId.isBlank()) {
            query.eq(InterviewSessionEntity::getResumeId, resumeId);
        }
        InterviewSessionEntity entity = interviewSessionMapper.selectOne(query);
        return entity == null ? null : toSessionView(entity);
    }

    /** 将 Java 保存的面试投影渲染为真实 PDF，不重新执行 Agent 工作流。 */
    @Override
    public byte[] exportInterviewReport(String userId, String sessionId) {
        return pdfReportService.createReport("模拟面试报告", toDetailView(requireOwnedSession(userId, sessionId)));
    }

    /** 关闭面试并删除 Agent 与 Java 两侧数据，不生成最终评价也不保留历史记录。 */
    @Override
    @Transactional
    public void deleteInterview(String userId, String sessionId) {
        InterviewSessionEntity entity = requireOwnedSession(userId, sessionId);
        requestSessionClosure(entity);
    }

    /** 标记会话不可继续使用并持久化关闭任务，重复请求复用同一任务而不重复关闭 Agent。 */
    private void requestSessionClosure(InterviewSessionEntity entity) {
        String sessionId = entity.getSessionId();
        InterviewCloseOutboxEntity existing = closeOutboxMapper.findActiveBySessionId(sessionId);
        if (existing != null) {
            if ("FAILED".equals(existing.getStatus()) && existing.getAttemptCount() >= MAX_CLOSE_RETRIES + 1) {
                existing.setStatus("PENDING");
                existing.setAttemptCount(0);
                existing.setNextAttemptAt(Instant.now());
                closeOutboxMapper.updateById(existing);
                entity.setStatus("CLOSING");
                entity.setUpdatedAt(Instant.now());
                interviewSessionMapper.updateById(entity);
            }
            return;
        }
        entity.setStatus("CLOSING");
        entity.setUpdatedAt(Instant.now());
        interviewSessionMapper.updateById(entity);
        InterviewCloseOutboxEntity event = new InterviewCloseOutboxEntity();
        event.setEventId(UUID.randomUUID().toString());
        event.setSessionId(sessionId);
        event.setUserId(entity.getUserId());
        event.setRunId(UUID.randomUUID().toString());
        event.setStatus("PENDING");
        event.setAttemptCount(0);
        event.setNextAttemptAt(Instant.now());
        closeOutboxMapper.insert(event);
    }

    /** 定时关闭已请求删除的 Agent 会话；成功后才移除 Java 会话和回合投影。 */
    @Scheduled(fixedDelay = 30_000L)
    public void processCloseOutbox() {
        closeOutboxMapper.selectList(Wrappers.<InterviewCloseOutboxEntity>lambdaQuery()
                .and(query -> query
                        .and(item -> item.in(InterviewCloseOutboxEntity::getStatus, List.of("PENDING", "FAILED"))
                                .le(InterviewCloseOutboxEntity::getNextAttemptAt, Instant.now()))
                        .or(item -> item.eq(InterviewCloseOutboxEntity::getStatus, "PROCESSING")
                                .lt(InterviewCloseOutboxEntity::getClaimedAt, Instant.now().minusSeconds(300))))
                .lt(InterviewCloseOutboxEntity::getAttemptCount, MAX_CLOSE_RETRIES + 1))
                .forEach(this::deliverCloseEvent);
    }

    private void deliverCloseEvent(InterviewCloseOutboxEntity event) {
        InterviewSessionEntity session = interviewSessionMapper.selectById(event.getSessionId());
        if (session == null) {
            event.setStatus("COMPLETED");
            closeOutboxMapper.updateById(event);
            return;
        }
        if (closeOutboxMapper.claim(event.getEventId()) != 1) {
            return;
        }
        try {
            AgentOperationRequest request = createRequest(event.getUserId(), event.getSessionId(), event.getRunId(),
                    promptService.render("Interview/close.txt", Map.of()), Map.of(), session.getStateVersion(),
                    "capability", "interview.close");
            agentCallService.execute(request);
            deleteLocalSession(event.getSessionId());
            event.setStatus("COMPLETED");
        } catch (RuntimeException error) {
            int attempt = event.getAttemptCount() + 1;
            event.setAttemptCount(attempt);
            event.setStatus("FAILED");
            event.setNextAttemptAt(Instant.now().plusMillis(CLOSE_RETRY_INTERVAL_MILLIS));
            session.setStatus("CLOSE_FAILED");
            session.setUpdatedAt(Instant.now());
            interviewSessionMapper.updateById(session);
        }
        closeOutboxMapper.updateById(event);
    }

    /** 定期清理由 Java 可见状态判断出的六小时无推进会话，保证 Agent 自动关闭后前端也不再阻塞新面试。 */
    @Scheduled(fixedDelay = 300000)
    public void closeInactiveSessions() {
        Instant threshold = Instant.now().minusSeconds(INACTIVITY_SECONDS);
        List<InterviewSessionEntity> sessions = interviewSessionMapper.selectList(
                new LambdaQueryWrapper<InterviewSessionEntity>()
                        .in(InterviewSessionEntity::getStatus, List.of("ACTIVE", "PAUSED"))
                        .lt(InterviewSessionEntity::getUpdatedAt, threshold)
        );
        for (InterviewSessionEntity session : sessions) {
            try {
                deleteInterview(session.getUserId(), session.getSessionId());
            } catch (RuntimeException ignored) {
                // 本轮无法关闭时保留 Java 记录，下一次定时扫描继续尝试，避免丢失可见状态。
            }
        }
    }

    /** 构造统一 Agent 请求，Java 只传递会话关联信息和业务自然语言，不暴露 Agent 内部流程。 */
    private AgentOperationRequest createRequest(
            String userId, String sessionId, String runId, String prompt,
            Map<String, Object> data, long stateVersion, String mode, String capability
    ) {
        AgentRequestContext context = new AgentRequestContext(
                "v1", UUID.randomUUID().toString(), runId, userId, sessionId, Instant.now()
        );
        return new AgentOperationRequest(context, mode, capability, prompt, data, null, stateVersion);
    }

    /** 按用户和会话共同条件读取实体，拒绝跨用户读取或修改。 */
    private InterviewSessionEntity requireOwnedSession(String userId, String sessionId) {
        InterviewSessionEntity entity = interviewSessionMapper.selectOne(
                new LambdaQueryWrapper<InterviewSessionEntity>()
                        .eq(InterviewSessionEntity::getSessionId, sessionId)
                        .eq(InterviewSessionEntity::getUserId, userId)
        );
        if (entity == null) {
            throw new IllegalStateException("面试会话不存在或不属于当前用户");
        }
        return entity;
    }

    /** 查询该用户当前是否已有活动面试，用于禁止刷新后创建第二个未完成会话。 */
    private InterviewSessionEntity findUnfinishedEntity(String userId) {
        return interviewSessionMapper.selectOne(
                new LambdaQueryWrapper<InterviewSessionEntity>()
                        .eq(InterviewSessionEntity::getUserId, userId)
                        .in(InterviewSessionEntity::getStatus, List.of("CREATING", "ACTIVE", "PAUSED"))
                        .orderByDesc(InterviewSessionEntity::getUpdatedAt)
                        .last("LIMIT 1")
        );
    }

    /**
     * 在创建链路任意一侧失败后尽力关闭 Agent 会话。
     *
     * 该操作不能覆盖创建失败的原始异常；Agent 侧不存在会话时会按幂等关闭处理。
     */
    private void compensateFailedCreation(String userId, String sessionId) {
        try {
            AgentOperationRequest request = createRequest(
                    userId, sessionId, UUID.randomUUID().toString(), promptService.render("Interview/close.txt", Map.of()),
                    Map.of(), 0, "capability", "interview.close"
            );
            agentCallService.execute(request);
        } catch (RuntimeException ignored) {
            // 补偿失败时不掩盖原始失败，Agent 后台的六小时清理仍可回收可能残留的会话。
        }
    }

    /** 删除 Java 侧会话和回合投影；只有 Agent 已关闭或确认关闭后才会调用。 */
    private void deleteLocalSession(String sessionId) {
        interviewSessionMapper.deleteById(sessionId);
    }

    /** 将 Agent 的公共进度和最终评价投影到 Java 展示实体。 */
    private void applyAgentData(InterviewSessionEntity entity, Map<String, Object> data) {
        if (data == null) {
            return;
        }
        Object contentValue = data.get("content");
        if (contentValue instanceof String value && !value.isBlank()) {
            entity.setCurrentQuestion(value);
        }
        Map<String, Object> progress = data.get("progress") instanceof Map<?, ?> rawProgress
                ? objectMapper.convertValue(rawProgress, Map.class) : Map.of();
        Object statusValue = progress.get("status");
        if (statusValue instanceof String value && !value.isBlank()) entity.setStatus(value);
        Object stageValue = progress.get("currentStage");
        if (stageValue instanceof String value && !value.isBlank()) entity.setCurrentStage(value);
        Object topicValue = progress.get("currentTopic");
        if (topicValue instanceof String value && !value.isBlank()) entity.setCurrentTopic(value);
        Object issuedValue = progress.get("totalQuestionCount");
        if (issuedValue instanceof Number value) entity.setIssuedQuestionCount(value.intValue());
        Object primaryValue = progress.get("currentPrimaryQuestionCount");
        if (primaryValue instanceof Number value) entity.setPrimaryQuestionCount(value.intValue());
        Object totalPrimaryValue = progress.get("totalPrimaryQuestionCount");
        if (totalPrimaryValue instanceof Number value) entity.setTotalPrimaryQuestionCount(value.intValue());
        Object followupValue = progress.get("currentFollowupCount");
        if (followupValue instanceof Number value) entity.setFollowupCount(value.intValue());
        Object budgetValue = progress.get("questionBudget");
        if (budgetValue instanceof Number value) entity.setTotalQuestions(value.intValue());
        else if (entity.getTotalQuestions() == 0) entity.setTotalQuestions(20);
        Map<String, Object> evaluation = data.get("finalEvaluation") instanceof Map<?, ?> rawEvaluation
                ? objectMapper.convertValue(rawEvaluation, Map.class) : Map.of();
        if (!evaluation.isEmpty()) {
            try {
                entity.setFinalEvaluationJson(objectMapper.writeValueAsString(evaluation));
            } catch (JsonProcessingException error) {
                throw new IllegalStateException("无法保存 Agent 最终评价", error);
            }
        }
    }

    /** 保存当前回答对应的上一道题和 Agent 返回的评价摘要，供前端刷新后恢复对话。 */
    private void saveAnswerTurn(InterviewSessionEntity entity, String answer, Map<String, Object> data) {
        InterviewTurnEntity turn = new InterviewTurnEntity();
        turn.setId(UUID.randomUUID().toString());
        turn.setSessionId(entity.getSessionId());
        turn.setTurnIndex(interviewTurnMapper.selectCount(
                new LambdaQueryWrapper<InterviewTurnEntity>()
                        .eq(InterviewTurnEntity::getSessionId, entity.getSessionId())
        ).intValue());
        turn.setStage(entity.getCurrentStage());
        turn.setQuestion(entity.getCurrentQuestion());
        turn.setAnswer(answer);
        Map<String, Object> evaluation = data.get("evaluation") instanceof Map<?, ?> rawEvaluation
                ? objectMapper.convertValue(rawEvaluation, Map.class) : Map.of();
        Object summaryValue = evaluation.get("summary");
        turn.setEvaluationSummary(summaryValue instanceof String value && !value.isBlank() ? value : null);
        Object scoreValue = evaluation.get("score");
        turn.setScore(scoreValue instanceof Number value ? value.intValue() : null);
        turn.setCreatedAt(Instant.now());
        interviewTurnMapper.insert(turn);
    }

    /** 将会话实体与回合转换成前端现有的统一详情结构。 */
    private Map<String, Object> toDetailView(InterviewSessionEntity entity) {
        List<Map<String, Object>> turns = interviewTurnMapper.selectList(
                        new LambdaQueryWrapper<InterviewTurnEntity>()
                                .eq(InterviewTurnEntity::getSessionId, entity.getSessionId())
                                .orderByAsc(InterviewTurnEntity::getTurnIndex)
                ).stream()
                .map(turn -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("index", turn.getTurnIndex());
                    item.put("stage", turn.getStage());
                    item.put("question", turn.getQuestion());
                    item.put("answer", turn.getAnswer());
                    item.put("evaluationSummary", turn.getEvaluationSummary());
                    item.put("score", turn.getScore());
                    return item;
                })
                .toList();
        return Map.of("session", toSessionView(entity), "turns", turns);
    }

    /** 生成前端列表和当前会话恢复所需的统一字段。 */
    private Map<String, Object> toSessionView(InterviewSessionEntity entity) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("sessionId", entity.getSessionId());
        view.put("resumeId", entity.getResumeId());
        view.put("interviewDirection", entity.getInterviewDirection());
        view.put("difficulty", entity.getDifficulty());
        view.put("totalQuestions", entity.getTotalQuestions() == 0 ? 20 : entity.getTotalQuestions());
        view.put("status", entity.getStatus());
        view.put("stateVersion", entity.getStateVersion());
        view.put("currentQuestion", entity.getCurrentQuestion());
        view.put("currentStage", entity.getCurrentStage());
        view.put("issuedQuestionCount", entity.getIssuedQuestionCount());
        view.put("primaryQuestionCount", entity.getPrimaryQuestionCount());
        view.put("totalPrimaryQuestionCount", entity.getTotalPrimaryQuestionCount());
        view.put("followupCount", entity.getFollowupCount());
        try {
            view.put("finalEvaluation", entity.getFinalEvaluationJson() == null || entity.getFinalEvaluationJson().isBlank()
                    ? Map.of() : objectMapper.readValue(entity.getFinalEvaluationJson(), Map.class));
        } catch (JsonProcessingException error) {
            view.put("finalEvaluation", Map.of());
        }
        view.put("createdAt", entity.getCreatedAt());
        view.put("updatedAt", entity.getUpdatedAt());
        return view;
    }
}
