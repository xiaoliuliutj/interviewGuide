from agent.Agents.models import AgentContext, AgentMessage
from agent.Common.Exceptions.agent_exception import AgentSessionConcurrencyError
from agent.Common.Configs.settings import AgentSettings
from agent.Common.Postgres.postgres_service import PostgresService
from agent.Common.Redis.redis_service import RedisService
from agent.Memory.memory_repository import MemoryRepository
from agent.Memory.memory_models import LongTermMemorySnapshot
from agent.Memory.memory_redis_store import MemoryRedisStore
from agent.LLM.llm_service import LlmService
from agent.utils.security.data_masker import DataMasker
import json
from agent.Common.results import AgentOperationResponse


class MemoryService:
    """按 Redis 优先、PostgreSQL 可重建的原则向 AgentLoop 提供分层记忆。"""

    def __init__(self, llmService: LlmService | None = None) -> None:
        """装配惰性基础设施，避免服务启动时因 Redis 或 PostgreSQL 未就绪而失败。"""
        settings = AgentSettings.from_environment()
        self.sessionStore = MemoryRedisStore(RedisService(settings))
        self.repository = MemoryRepository(PostgresService(settings))
        self.llmService = llmService
        self.dataMasker = DataMasker()

    async def close(self) -> None:
        """关闭 Redis、PostgreSQL 与摘要模型客户端，保证进程优雅退出不遗留连接。"""
        await self.sessionStore.redisService.close()
        await self.repository.postgresService.close()
        if self.llmService is not None:
            await self.llmService.close()

    async def invalidateMemoryCache(self, *keys: str) -> None:
        """在数据库写入后尽力失效记忆缓存，缓存故障不能回滚已提交的事实数据。"""
        try:
            client = await self.sessionStore.redisService.client()
            await client.delete(*keys)
        except Exception:
            return

    async def loadMemory(self, context: AgentContext) -> list[AgentMessage]:
        """按角色构造长期事实、滚动摘要和原始对话，Redis 缺失时从数据库恢复。"""
        try:
            snapshot = await self.sessionStore.loadSnapshot(context.request.context.conversation_id)
        except Exception:
            snapshot = None
        if snapshot is None:
            snapshot = await self.repository.loadSessionSnapshot(
                context.request.context.conversation_id,
            )
            try:
                await self.sessionStore.saveSnapshot(
                    context.request.context.conversation_id,
                    snapshot,
                )
            except Exception:
                pass

        userId = context.request.context.principal_id
        resumeId = context.request.payload.get("resumeId")
        profileKey = f"agent:user:{userId}:profile"
        overviewKey = f"agent:user:{userId}:interviewOverview"
        resumeKey = f"agent:resume:{userId}:{resumeId}:memory" if resumeId else None
        try:
            client = await self.sessionStore.redisService.client()
            cachedProfile, cachedOverview = await client.mget(profileKey, overviewKey)
            cachedResume = await client.get(resumeKey) if resumeKey else None
        except Exception:
            client = None
            cachedProfile = cachedOverview = cachedResume = None
        if cachedProfile is None or cachedOverview is None or (resumeKey and cachedResume is None):
            longTerm = await self.repository.loadLongTermMemory(userId, resumeId)
            if client is not None:
                try:
                    pipeline = client.pipeline(transaction=True)
                    pipeline.set(profileKey, longTerm.userProfile or "", ex=86400)
                    pipeline.set(overviewKey, longTerm.interviewOverview or "", ex=86400)
                    if resumeKey:
                        pipeline.set(resumeKey, longTerm.resumeMemory or "", ex=86400)
                    await pipeline.execute()
                except Exception:
                    pass
        else:
            longTerm = LongTermMemorySnapshot(
                cachedProfile or None,
                cachedResume or None,
                cachedOverview or None,
            )
        messages: list[AgentMessage] = []
        for item in (
            longTerm.userProfile,
            longTerm.resumeMemory,
            longTerm.interviewOverview,
            snapshot.rollingSummary,
        ):
            if item:
                messages.append(AgentMessage(role="system", content=item))
        messages.extend(snapshot.messages)
        return messages

    async def initializeSession(self, context: AgentContext) -> None:
        """在面试初始化请求到达时创建 Agent 会话事实记录和空的 Redis 运行态。"""
        await self.repository.initializeSession(
            context.request.context.conversation_id,
            context.request.context.principal_id,
            context.request.payload.get("resumeId"),
        )

    async def startTurn(self, context: AgentContext) -> str:
        """同时登记 Redis 租约和数据库 activeRunId，拒绝同一会话的并发面试回合。"""
        sessionId = context.request.context.conversation_id
        runId = context.request.context.run_id
        try:
            acquired = await self.sessionStore.acquireRun(sessionId, runId)
        except Exception:
            # Redis 不可用时仍由 PostgreSQL activeRun 和乐观版本承担并发控制。
            context.redisLeaseEnabled = False
            acquired = True
        if not acquired:
            if await self.sessionStore.loadActiveRun(sessionId) == runId:
                return "EXISTING_PROCESSING"
            raise AgentSessionConcurrencyError("当前面试会话已有任务正在执行")
        try:
            status = await self.repository.claimRun(
                sessionId,
                context.request.context.principal_id,
                runId,
                context.request.task_type.value,
                context.request.state_version,
            )
        except Exception:
            if context.redisLeaseEnabled:
                await self.sessionStore.releaseRun(sessionId, runId)
            raise
        if status == "PROCESSING":
            return status
        if status == "EXISTING_PROCESSING":
            if context.redisLeaseEnabled:
                await self.sessionStore.releaseRun(sessionId, runId)
            return status
        if status in {"EXISTING_COMPLETED", "EXISTING_FAILED"}:
            if context.redisLeaseEnabled:
                await self.sessionStore.releaseRun(sessionId, runId)
            return status
        if status.startswith("EXISTING_"):
            if context.redisLeaseEnabled:
                await self.sessionStore.releaseRun(sessionId, runId)
            raise AgentSessionConcurrencyError(f"runId 已存在，当前状态为 {status}")
        if status != "PROCESSING":
            if context.redisLeaseEnabled:
                await self.sessionStore.releaseRun(sessionId, runId)
            raise AgentSessionConcurrencyError("会话版本已变化或已有任务正在执行")

        return status

    async def finishTurn(self, context: AgentContext, assistantContent: str) -> int:
        """持久化一轮消息并递增版本，随后刷新 Redis 快照以支持下一轮低延迟读取。"""
        userContent = self.dataMasker.maskText(str(context.request.payload.get("answer", "")))
        assistantContent = self.dataMasker.maskText(assistantContent)
        version = await self.repository.appendTurn(
            context.request.context.conversation_id,
            context.request.context.run_id,
            context.request.state_version,
            userContent,
            assistantContent,
        )
        snapshot = await self.repository.loadSessionSnapshot(context.request.context.conversation_id)
        await self.refreshSummary(context.request.context.conversation_id, snapshot)
        snapshot = await self.repository.loadSessionSnapshot(context.request.context.conversation_id)
        try:
            await self.sessionStore.saveSnapshot(context.request.context.conversation_id, snapshot)
        except Exception:
            pass
        finally:
            try:
                await self.sessionStore.releaseRun(
                    context.request.context.conversation_id,
                    context.request.context.run_id,
                )
            except Exception:
                pass
        return version

    async def renewTurnLease(self, context: AgentContext) -> None:
        """在 AgentLoop 的每轮模型调用前续租，确保长运行任务不会失去会话执行权。"""
        if not context.redisLeaseEnabled:
            databaseRenewed = await self.repository.renewRunLease(
                context.request.context.conversation_id,
                context.request.context.run_id,
            )
            if not databaseRenewed:
                raise AgentSessionConcurrencyError("当前任务已失去数据库会话执行权")
            return
        renewed = await self.sessionStore.renewRun(
            context.request.context.conversation_id,
            context.request.context.run_id,
        )
        if not renewed:
            raise AgentSessionConcurrencyError("当前任务已失去会话执行权")

        databaseRenewed = await self.repository.renewRunLease(
            context.request.context.conversation_id,
            context.request.context.run_id,
        )
        if not databaseRenewed:
            raise AgentSessionConcurrencyError("当前任务已失去数据库会话执行权")

    async def abortTurn(self, context: AgentContext) -> None:
        """在任意失败路径释放 Redis 与数据库执行权，使用户可安全发起下一次回合。"""
        sessionId = context.request.context.conversation_id
        runId = context.request.context.run_id
        try:
            await self.repository.abortRun(sessionId, runId)
        finally:
            await self.sessionStore.releaseRun(sessionId, runId)

    async def saveRunResult(self, response: AgentOperationResponse) -> None:
        """将最终标准响应写入数据库，供同一 runId 的重试直接重放。"""
        serialized = response.model_dump_json(by_alias=True)
        if response.status == "COMPLETED":
            await self.repository.completeRun(response.run_id, serialized)
        else:
            await self.repository.failRun(response.run_id, serialized)

    async def loadRunResult(self, runId: str, userId: str, sessionId: str) -> AgentOperationResponse | None:
        """读取相同 runId 的最终响应，网络重试时直接重放而不重复执行 AgentLoop。"""
        record = await self.repository.loadRunResult(runId, userId, sessionId)
        if record is None or record["status"] == "PROCESSING" or record["result_json"] is None:
            return None
        return AgentOperationResponse.model_validate(record["result_json"])

    async def refreshSummary(
        self,
        sessionId: str,
        snapshot,
    ) -> None:
        """窗口超过五轮时总结淘汰消息；失败仅进入 Outbox 补偿，不阻断已完成的面试回合。"""
        try:
            _, expiredRows, _ = await self.repository.loadSummaryWorkset(sessionId)
            if not expiredRows:
                return
            if self.llmService is None:
                self.llmService = LlmService()
            summary = await self.llmService.summarizeConversation(
                snapshot.rollingSummary,
                [f"{row['role']}: {row['content_masked']}" for row in expiredRows],
            )
            await self.repository.saveSummary(
                sessionId,
                summary,
                int(expiredRows[-1]["sequence_number"]),
            )
        except Exception:
            # 摘要属于辅助记忆，不能让已完成的面试回合变成失败；Outbox 写入失败时
            # 仍保留原始消息，后续可由定时扫描按摘要边界重新计算。
            try:
                await self.repository.enqueueSummaryRetry(sessionId)
            except Exception:
                return

    async def retrySummary(self, sessionId: str) -> None:
        """由 RabbitMQ 补偿消费者重新加载数据库快照并再次执行滚动摘要。"""
        snapshot = await self.repository.loadSessionSnapshot(sessionId)
        await self.refreshSummary(sessionId, snapshot)

    async def saveResumeEvaluation(
        self,
        userId: str,
        resumeId: str,
        evaluation: dict[str, object],
    ) -> None:
        """在简历评估完成后保存脱敏评估结果，长期记忆只保留结构化结论。"""
        summary = str(evaluation.get("summary", ""))
        await self.repository.saveResumeMemory(
            userId,
            resumeId,
            json.dumps(self.dataMasker.maskObject(evaluation), ensure_ascii=False),
            summary,
        )
        await self.invalidateMemoryCache(f"agent:resume:{userId}:{resumeId}:memory")

    async def deleteResumeMemory(self, userId: str, resumeId: str) -> None:
        """删除长期简历记忆与 Redis 缓存，调用方必须已在 Java 完成资源归属校验。"""
        await self.repository.deleteResumeMemory(userId, resumeId)
        await self.invalidateMemoryCache(f"agent:resume:{userId}:{resumeId}:memory")

    async def saveUserProfile(self, userId: str, profile: dict[str, object]) -> None:
        """保存用户画像并失效 Redis 副本，确保下一次读取到数据库最新版本。"""
        maskedProfile = self.dataMasker.maskObject(profile)
        await self.repository.saveUserProfile(
            userId,
            json.dumps(maskedProfile, ensure_ascii=False),
            str(maskedProfile.get("summary", "")),
        )
        await self.invalidateMemoryCache(f"agent:user:{userId}:profile")

    async def saveInterviewOverview(self, userId: str, overview: dict[str, object]) -> None:
        """保存用户历史面试聚合摘要并失效缓存，避免新旧结论同时存在。"""
        maskedOverview = self.dataMasker.maskObject(overview)
        await self.repository.saveInterviewOverview(
            userId,
            json.dumps(maskedOverview, ensure_ascii=False),
            str(maskedOverview.get("summary", "")),
        )
        await self.invalidateMemoryCache(f"agent:user:{userId}:interviewOverview")

    async def saveInterviewCompletion(self, userId: str, sessionId: str, result: dict[str, object]) -> None:
        """保存脱敏单场面试记忆，并失效用户面试总览缓存以便异步聚合更新。"""
        maskedResult = self.dataMasker.maskObject(result)
        await self.repository.saveInterviewMemory(
            userId, sessionId, json.dumps(maskedResult, ensure_ascii=False), str(maskedResult.get("summary", "")),
        )
        memories = await self.repository.loadInterviewMemories(userId)
        overview = {
            "interviews": memories,
            "count": len(memories),
            "summary": "\n".join(item["summary"] for item in memories if item["summary"]),
        }
        await self.repository.saveInterviewOverview(
            userId,
            json.dumps(overview, ensure_ascii=False),
            overview["summary"],
        )
        await self.invalidateMemoryCache(f"agent:user:{userId}:interviewOverview")

    async def deleteInterviewMemory(self, userId: str, sessionId: str) -> None:
        """删除已删除面试对应的长期记忆与运行时 Redis 上下文。"""
        await self.repository.assertSessionOwner(sessionId, userId)
        await self.repository.deleteInterviewMemory(userId, sessionId)
        memories = await self.repository.loadInterviewMemories(userId)
        overview = {
            "interviews": memories,
            "count": len(memories),
            "summary": "\n".join(item["summary"] for item in memories if item["summary"]),
        }
        await self.repository.saveInterviewOverview(
            userId,
            json.dumps(overview, ensure_ascii=False),
            overview["summary"],
        )
        await self.invalidateMemoryCache(
            f"agent:session:{sessionId}:runtime",
            f"agent:session:{sessionId}:recentMessages",
            f"agent:session:{sessionId}:activeRun",
            f"agent:user:{userId}:interviewOverview",
        )

    async def discardSessionRuntime(self, sessionId: str) -> None:
        """删除未完成会话的 Redis 快照和运行租约；该操作不触碰任何用户长期记忆。"""
        await self.invalidateMemoryCache(
            f"agent:session:{sessionId}:runtime",
            f"agent:session:{sessionId}:recentMessages",
            f"agent:session:{sessionId}:activeRun",
        )
