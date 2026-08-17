import json

from agent.Common.AgentModels import AgentMessage
from agent.Common.Redis.RedisService import RedisService
from agent.Memory.memoryModels import SessionMemorySnapshot


class MemoryRedisStore:
    """管理记忆模块在 Redis 中的短期会话快照和回合租约。

    该类不负责创建 Redis 连接，也不提供其他模块通用缓存能力；通用连接能力位于
    Common/Redis/redis_service.py。这里的所有 key 都属于 Agent 记忆会话状态。
    """

    def __init__(self, redisService: RedisService, sessionTtlSeconds: int = 86400) -> None:
        """保存 Redis 适配器与可重建短期记忆的过期时间，默认保留二十四小时。"""
        self.redisService = redisService
        self.sessionTtlSeconds = sessionTtlSeconds

    async def loadSnapshot(self, sessionId: str) -> SessionMemorySnapshot | None:
        """读取会话摘要和最近消息；缓存缺失时由上层从 PostgreSQL 重建。"""
        client = await self.redisService.client()
        runtime = await client.hgetall(f"agent:session:{sessionId}:runtime")
        rawMessages = await client.get(f"agent:session:{sessionId}:recentMessages")
        if not runtime or rawMessages is None:
            return None
        messages = [AgentMessage(**item) for item in json.loads(rawMessages)]
        return SessionMemorySnapshot(
            stateVersion=int(runtime["stateVersion"]),
            rollingSummary=runtime.get("rollingSummary") or None,
            messages=messages,
            summarizedUntilSequence=int(runtime.get("summarizedUntilSequence", 0)),
        )

    async def saveSnapshot(self, sessionId: str, snapshot: SessionMemorySnapshot) -> None:
        """原子写入短期记忆快照，并同时刷新运行态与消息窗口的 TTL。"""
        client = await self.redisService.client()
        runtimeKey = f"agent:session:{sessionId}:runtime"
        messagesKey = f"agent:session:{sessionId}:recentMessages"
        serializedMessages = json.dumps(
            [message.__dict__ for message in snapshot.messages],
            ensure_ascii=False,
        )
        pipeline = client.pipeline(transaction=True)
        pipeline.hset(
            runtimeKey,
            mapping={
                "stateVersion": snapshot.stateVersion,
                "rollingSummary": snapshot.rollingSummary or "",
                "summarizedUntilSequence": snapshot.summarizedUntilSequence,
            },
        )
        pipeline.set(messagesKey, serializedMessages)
        pipeline.expire(runtimeKey, self.sessionTtlSeconds)
        pipeline.expire(messagesKey, self.sessionTtlSeconds)
        await pipeline.execute()

    async def acquireRun(self, sessionId: str, runId: str) -> bool:
        """原子抢占会话执行租约，避免同一会话并发进入多个 AgentLoop。"""
        client = await self.redisService.client()
        return bool(await client.set(f"agent:session:{sessionId}:activeRun", runId, nx=True, ex=90))

    async def loadActiveRun(self, sessionId: str) -> str | None:
        """读取当前租约持有者，用于识别相同 runId 的处理中重试。"""
        client = await self.redisService.client()
        return await client.get(f"agent:session:{sessionId}:activeRun")

    async def releaseRun(self, sessionId: str, runId: str) -> None:
        """仅释放当前 run 持有的租约，防止旧任务误删新任务的锁。"""
        client = await self.redisService.client()
        key = f"agent:session:{sessionId}:activeRun"
        await client.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('DEL', KEYS[1]) else return 0 end",
            1,
            key,
            runId,
        )

    async def renewRun(self, sessionId: str, runId: str) -> bool:
        """仅允许当前持有者续租，避免长模型调用后错误并发进入会话。"""
        client = await self.redisService.client()
        key = f"agent:session:{sessionId}:activeRun"
        result = await client.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('EXPIRE', KEYS[1], ARGV[2]) else return 0 end",
            1,
            key,
            runId,
            90,
        )
        return bool(result)
