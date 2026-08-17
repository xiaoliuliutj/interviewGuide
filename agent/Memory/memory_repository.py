import json

from agent.Agents.models import AgentMessage
from agent.Common.Exceptions.agent_exception import (
    AgentSessionNotFoundError,
    AgentSessionStateError,
    MemoryVersionConflictError,
)
from agent.Common.Postgres.postgres_service import PostgresService
from agent.Memory.memory_models import LongTermMemorySnapshot, SessionMemorySnapshot


class MemoryRepository:
    """从 PostgreSQL 读取可用于重建 Redis 的短期记忆和长期记忆事实数据。"""

    def __init__(self, postgresService: PostgresService) -> None:
        """保存 PostgreSQL 连接服务，所有查询均在实际调用时才建立连接。"""
        self.postgresService = postgresService

    async def loadSessionSnapshot(self, sessionId: str) -> SessionMemorySnapshot:
        """读取最新滚动摘要和最近十条消息，为 Redis 缓存丢失提供重建数据。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            session = await connection.fetchrow(
                "SELECT state_version FROM agent_session WHERE session_id = $1 AND deleted_at IS NULL",
                sessionId,
            )
            if session is None:
                raise AgentSessionNotFoundError(f"会话 {sessionId} 不存在或已删除")
            summary = await connection.fetchrow(
                "SELECT summary_content, summarized_until_sequence FROM agent_session_summary "
                "WHERE session_id = $1 AND status = 'READY' "
                "ORDER BY version DESC LIMIT 1",
                sessionId,
            )
            rows = await connection.fetch(
                "SELECT role, content_masked FROM agent_session_message "
                "WHERE session_id = $1 AND sequence_number > $2 "
                "ORDER BY sequence_number DESC LIMIT 10",
                sessionId,
                summary["summarized_until_sequence"] if summary else 0,
            )
        messages = [
            AgentMessage(role=row["role"], content=row["content_masked"])
            for row in reversed(rows)
        ]
        return SessionMemorySnapshot(
            stateVersion=session["state_version"],
            rollingSummary=summary["summary_content"] if summary else None,
            messages=messages,
            summarizedUntilSequence=summary["summarized_until_sequence"] if summary else 0,
        )

    async def initializeSession(self, sessionId: str, userId: str, resumeId: str | None) -> None:
        """创建 Agent 内部会话记录，使第一轮面试具备可持久化状态和版本起点。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            created = await connection.fetchval(
                "INSERT INTO agent_session(session_id, user_id, resume_id, status) VALUES($1, $2, $3, 'ACTIVE') "
                "ON CONFLICT(session_id) DO NOTHING RETURNING session_id",
                sessionId,
                userId,
                resumeId,
            )
            if created is not None:
                return
            owner = await connection.fetchval(
                "SELECT user_id FROM agent_session WHERE session_id = $1 AND deleted_at IS NULL",
                sessionId,
            )
            if owner != userId:
                raise AgentSessionStateError("会话不属于当前用户，拒绝覆盖会话归属")
            await connection.execute(
                "UPDATE agent_session SET resume_id = COALESCE($2, resume_id), updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = $1 AND user_id = $3",
                sessionId,
                resumeId,
                userId,
            )

    async def claimRun(self, sessionId: str, userId: str, runId: str, taskType: str, expectedVersion: int) -> str:
        """创建或读取 run 记录，实现同一 runId 的网络重试幂等与不同 run 的会话互斥。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchval(
                    "SELECT status FROM agent_run WHERE run_id = $1 AND session_id = $2 AND user_id = $3",
                    runId, sessionId, userId,
                )
                if existing is not None:
                    return f"EXISTING_{existing}"
                foreign = await connection.fetchval("SELECT 1 FROM agent_run WHERE run_id = $1", runId)
                if foreign is not None:
                    return "CONFLICT"
                updated = await connection.fetchval(
                    "UPDATE agent_session SET active_run_id = $2, active_run_heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "WHERE session_id = $1 AND user_id = $3 AND state_version = $4 AND "
                    "(active_run_id IS NULL OR active_run_heartbeat_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes') "
                    "AND deleted_at IS NULL RETURNING session_id",
                    sessionId, runId, userId, expectedVersion,
                )
                if updated is None:
                    return "CONFLICT"
                await connection.execute(
                    "INSERT INTO agent_run(run_id, session_id, user_id, task_type, expected_state_version, status) "
                    "VALUES($1, $2, $3, $4, $5, 'PROCESSING')",
                    runId, sessionId, userId, taskType, expectedVersion,
                )
        return "PROCESSING"

    async def loadLongTermMemory(
        self,
        userId: str,
        resumeId: str | None,
    ) -> LongTermMemorySnapshot:
        """读取当前有效的用户画像、简历记忆与面试总览，避免加载原始敏感资料。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            profile = await connection.fetchval(
                "SELECT summary_text FROM agent_user_profile_memory "
                "WHERE user_id = $1 AND is_current AND deleted_at IS NULL",
                userId,
            )
            overview = await connection.fetchval(
                "SELECT summary_text FROM agent_user_interview_overview "
                "WHERE user_id = $1 AND is_current AND deleted_at IS NULL",
                userId,
            )
            resume = None
            if resumeId is not None:
                resume = await connection.fetchval(
                    "SELECT summary_text FROM agent_resume_memory "
                    "WHERE user_id = $1 AND resume_id = $2 "
                    "AND is_current AND deleted_at IS NULL",
                    userId,
                    resumeId,
                )
        return LongTermMemorySnapshot(profile, resume, overview)

    async def loadResumeMemoryDetail(self, userId: str, resumeId: str | None) -> dict[str, object] | None:
        """读取指定简历的结构化评估快照，供面试规划使用而不在每轮注入原始简历正文。"""
        if resumeId is None:
            return None
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            content = await connection.fetchval(
                "SELECT content_json FROM agent_resume_memory WHERE user_id=$1 AND resume_id=$2 "
                "AND is_current AND deleted_at IS NULL",
                userId,
                resumeId,
            )
        return dict(content) if content is not None else None

    async def assertSessionOwner(self, sessionId: str, userId: str) -> None:
        """校验会话归属，防止删除缓存等操作跨用户影响其他会话。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            owner = await connection.fetchval(
                "SELECT user_id FROM agent_session WHERE session_id = $1 AND deleted_at IS NULL",
                sessionId,
            )
        if owner is None:
            raise AgentSessionStateError("会话不存在或已删除")
        if owner != userId:
            raise AgentSessionStateError("会话不属于当前用户")

    async def appendTurn(
        self,
        sessionId: str,
        runId: str,
        expectedVersion: int,
        userContent: str,
        assistantContent: str,
    ) -> int:
        """以乐观锁提交一轮完整对话，保证旧 run 不能覆盖已经推进的会话版本。"""
        import hashlib

        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                updated = await connection.fetchval(
                    "UPDATE agent_session SET state_version = state_version + 1, active_run_id = NULL, active_run_heartbeat_at = NULL, "
                    "updated_at = CURRENT_TIMESTAMP WHERE session_id = $1 AND state_version = $2 "
                    "AND active_run_id = $3 AND deleted_at IS NULL RETURNING state_version",
                    sessionId,
                    expectedVersion,
                    runId,
                )
                if updated is None:
                    raise MemoryVersionConflictError("会话版本或 activeRunId 不匹配，拒绝提交过期任务结果")
                sequence = await connection.fetchval(
                    "SELECT COALESCE(MAX(sequence_number), 0) FROM agent_session_message WHERE session_id = $1",
                    sessionId,
                )
                for offset, role, content in ((1, "user", userContent), (2, "assistant", assistantContent)):
                    await connection.execute(
                        "INSERT INTO agent_session_message(session_id, run_id, turn_number, sequence_number, role, content_masked, content_hash) "
                        "VALUES($1, $2, $3, $4, $5, $6, $7)",
                        sessionId,
                        runId,
                        (sequence // 2) + 1,
                        sequence + offset,
                        role,
                        content,
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
        return updated

    async def completeRun(self, runId: str, resultJson: str) -> None:
        """保存完成 run 的标准响应，使网络重试能够返回原结果而不是重复调用模型。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_run SET status = 'COMPLETED', result_json = $2::jsonb, completed_at = CURRENT_TIMESTAMP "
                "WHERE run_id = $1 AND status = 'PROCESSING'",
                runId,
                resultJson,
            )

    async def failRun(self, runId: str, resultJson: str) -> None:
        """保存失败 run 的结构化响应，避免网络重试反复执行已失败任务。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_run SET status = 'FAILED', result_json = $2::jsonb, completed_at = CURRENT_TIMESTAMP "
                "WHERE run_id = $1 AND status = 'PROCESSING'",
                runId,
                resultJson,
            )

    async def loadRunResult(self, runId: str, userId: str, sessionId: str):
        """读取已完成或失败 run 的持久化结果，供相同 runId 幂等重放。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            return await connection.fetchrow(
                "SELECT status, result_json FROM agent_run WHERE run_id = $1 AND user_id = $2 AND session_id = $3",
                runId,
                userId,
                sessionId,
            )

    async def activateRun(self, sessionId: str, runId: str, expectedVersion: int) -> bool:
        """在数据库中登记 activeRunId，作为 Redis 租约失效后的最终并发防线。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE agent_session SET active_run_id = $2, active_run_heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = $1 AND state_version = $3 AND active_run_id IS NULL "
                "AND deleted_at IS NULL RETURNING session_id",
                sessionId,
                runId,
                expectedVersion,
            )
        return updated is not None

    async def abortRun(self, sessionId: str, runId: str) -> None:
        """失败或取消时清除相同 runId 的 activeRunId，避免会话永久处于处理中状态。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_session SET active_run_id = NULL, active_run_heartbeat_at = NULL, updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = $1 AND active_run_id = $2",
                sessionId,
                runId,
            )

    async def renewRunLease(self, sessionId: str, runId: str) -> bool:
        """刷新数据库侧执行心跳，使进程崩溃后的陈旧 activeRun 可以被后续请求回收。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE agent_session SET active_run_heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = $1 AND active_run_id = $2 AND deleted_at IS NULL RETURNING session_id",
                sessionId,
                runId,
            )
        return updated is not None

    async def saveSummary(self, sessionId: str, summary: str, sequence: int) -> None:
        """以递增版本保存滚动摘要，旧摘要保留以支持审计和回滚。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO agent_session_summary(session_id, version, summarized_until_sequence, summary_content, status) "
                "SELECT $1, COALESCE(MAX(version), 0) + 1, $2, $3, 'READY' "
                "FROM agent_session_summary WHERE session_id = $1",
                sessionId,
                sequence,
                summary,
            )

    async def loadSummaryWorkset(self, sessionId: str, keepMessages: int = 6):
        """读取尚未进入滚动摘要的消息，并保留窗口末尾消息不摘要。

        通过数据库序号计算边界，避免用 Redis 列表长度代替真实 sequence_number，
        从而在缓存失效、重复重试或多实例运行时仍能得到稳定的摘要范围。
        """
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            boundary = await connection.fetchval(
                "SELECT COALESCE(MAX(summarized_until_sequence), 0) FROM agent_session_summary "
                "WHERE session_id = $1 AND status = 'READY'", sessionId,
            )
            rows = await connection.fetch(
                "SELECT sequence_number, role, content_masked FROM agent_session_message "
                "WHERE session_id = $1 AND sequence_number > $2 ORDER BY sequence_number",
                sessionId, boundary,
            )
        if len(rows) <= keepMessages:
            return boundary, [], []
        expired = list(rows[:-keepMessages])
        recent = list(rows[-keepMessages:])
        return boundary, expired, recent

    async def enqueueSummaryRetry(self, sessionId: str) -> None:
        """在摘要失败时写入 Outbox，后台消费者可安全地重复补偿该任务。"""
        import uuid

        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO agent_outbox_event(event_id, event_type, aggregate_id, payload) "
                "VALUES($1, 'SESSION_SUMMARY_RETRY', $2, $3::jsonb)",
                uuid.uuid4(),
                sessionId,
                json.dumps({"reason": "summary_failed", "aggregateId": sessionId}),
            )

    async def saveResumeMemory(
        self,
        userId: str,
        resumeId: str,
        contentJson: str,
        summary: str,
    ) -> None:
        """版本化保存脱敏后的简历评估记忆，并原子切换当前有效版本。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE agent_resume_memory SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP "
                    "WHERE user_id = $1 AND resume_id = $2 AND is_current",
                    userId,
                    resumeId,
                )
                await connection.execute(
                    "INSERT INTO agent_resume_memory(user_id, resume_id, version, content_json, summary_text, source) "
                    "SELECT $1, $2, COALESCE(MAX(version), 0) + 1, $3::jsonb, $4, 'RESUME_EVALUATION' "
                    "FROM agent_resume_memory WHERE user_id = $1 AND resume_id = $2",
                    userId,
                    resumeId,
                    contentJson,
                    summary,
                )

    async def deleteResumeMemory(self, userId: str, resumeId: str) -> None:
        """逻辑删除指定用户的简历派生记忆，防止跨用户删除资源。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_resume_memory SET deleted_at = CURRENT_TIMESTAMP, is_current = FALSE "
                "WHERE user_id = $1 AND resume_id = $2 AND deleted_at IS NULL",
                userId,
                resumeId,
            )

    async def saveUserProfile(self, userId: str, contentJson: str, summary: str) -> None:
        """追加用户画像版本并切换当前版本，保留旧版本以支持审计和回滚。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE agent_user_profile_memory SET is_current = FALSE WHERE user_id = $1 AND is_current",
                    userId,
                )
                await connection.execute(
                    "INSERT INTO agent_user_profile_memory(user_id, version, content_json, summary_text, source) "
                    "SELECT $1, COALESCE(MAX(version), 0) + 1, $2::jsonb, $3, 'USER_PROFILE' "
                    "FROM agent_user_profile_memory WHERE user_id = $1",
                    userId,
                    contentJson,
                    summary,
                )

    async def saveInterviewOverview(self, userId: str, contentJson: str, summary: str) -> None:
        """追加用户面试总览版本，供下一场面试加载长期表现趋势。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE agent_user_interview_overview SET is_current = FALSE WHERE user_id = $1 AND is_current",
                    userId,
                )
                await connection.execute(
                    "INSERT INTO agent_user_interview_overview(user_id, version, content_json, summary_text, source) "
                    "SELECT $1, COALESCE(MAX(version), 0) + 1, $2::jsonb, $3, 'INTERVIEW_OVERVIEW' "
                    "FROM agent_user_interview_overview WHERE user_id = $1",
                    userId,
                    contentJson,
                    summary,
                )

    async def saveInterviewMemory(self, userId: str, sessionId: str, contentJson: str, summary: str) -> None:
        """保存单场已完成面试的脱敏摘要，作为后续用户面试总览的可追溯来源。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO agent_interview_memory(user_id, session_id, content_json, summary_text, source) "
                "VALUES($1, $2, $3::jsonb, $4, 'INTERVIEW_COMPLETION') "
                "ON CONFLICT(user_id, session_id) DO UPDATE SET content_json = EXCLUDED.content_json, "
                "summary_text = EXCLUDED.summary_text, deleted_at = NULL",
                userId, sessionId, contentJson, summary,
            )

    async def loadInterviewMemories(self, userId: str) -> list[dict[str, str]]:
        """读取用户未删除的单场面试摘要，供总览记忆重新聚合。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT session_id, summary_text FROM agent_interview_memory "
                "WHERE user_id = $1 AND deleted_at IS NULL ORDER BY created_at",
                userId,
            )
        return [{"sessionId": str(row["session_id"]), "summary": row["summary_text"]} for row in rows]

    async def deleteInterviewMemory(self, userId: str, sessionId: str) -> None:
        """按用户和会话逻辑删除单场面试派生记忆，防止跨用户资源清理。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_interview_memory SET deleted_at = CURRENT_TIMESTAMP "
                "WHERE user_id = $1 AND session_id = $2 AND deleted_at IS NULL",
                userId, sessionId,
            )

    async def loadPendingEvents(self, limit: int = 50):
        """读取待投递 Outbox 事件，发布器可重复扫描而不会遗漏数据库已提交的事件。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    "SELECT event_id, event_type, aggregate_id, payload FROM agent_outbox_event "
                    "WHERE status = 'PENDING' OR (status = 'PROCESSING' "
                    "AND claimed_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes') "
                    "ORDER BY created_at LIMIT $1 FOR UPDATE SKIP LOCKED",
                    limit,
                )
                for row in rows:
                    await connection.execute(
                        "UPDATE agent_outbox_event SET status = 'PROCESSING', claimed_at = CURRENT_TIMESTAMP, "
                        "attempt_count = attempt_count + 1 WHERE event_id = $1",
                        row["event_id"],
                    )
                return rows

    async def markEventPublished(self, eventId: object) -> None:
        """仅在 RabbitMQ 确认发布后标记事件，失败事件会保留为 PENDING 供下次补偿。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_outbox_event SET status = 'PUBLISHED', published_at = CURRENT_TIMESTAMP, claimed_at = NULL "
                "WHERE event_id = $1 AND status = 'PROCESSING'",
                eventId,
            )

    async def resetEventPending(self, eventId: object) -> None:
        """发布失败时归还事件领取状态，供后续扫描重新投递。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_outbox_event SET status = 'PENDING', claimed_at = NULL "
                "WHERE event_id = $1 AND status = 'PROCESSING'",
                eventId,
            )
