import json
import math
from agent.Common.Redis.RedisService import RedisService
from agent.RAG.ragModels import RagSearchResult


class RagSessionCache:
    """面试期间的临时 RAG 结果缓存，不替代 PostgreSQL 正式数据。"""
    def __init__(self, redisService: RedisService, ttlSeconds: int = 1800) -> None:
        self.redisService, self.ttlSeconds = redisService, ttlSeconds

    async def load(self, sessionId: str, scopeKey: str, queryVector: list[float], threshold: float) -> list[str] | None:
        """用余弦相似度判断缓存查询是否足够相关。"""
        client = await self.redisService.client()
        raw = await client.get(f"agent:rag:session:{sessionId}:{scopeKey}:results")
        if not raw:
            return None
        payload = json.loads(raw)
        if not payload or self.cosine(queryVector, payload[0]["queryVector"]) < threshold:
            return None
        return [item["content"] for item in payload]

    async def loadEntries(
        self,
        sessionId: str,
        scopeKey: str,
        queryVector: list[float],
        threshold: float,
    ) -> list[dict[str, object]] | None:
        """读取带来源元数据的缓存，供当前 run 补写来源追踪。"""
        client = await self.redisService.client()
        raw = await client.get(f"agent:rag:session:{sessionId}:{scopeKey}:results")
        if not raw:
            return None
        payload = json.loads(raw)
        if not payload or self.cosine(queryVector, payload[0]["queryVector"]) < threshold:
            return None
        return payload

    async def save(self, sessionId: str, scopeKey: str, queryVector: list[float], results: list[RagSearchResult]) -> None:
        """保存检索正文和内部来源元数据，并刷新 TTL。"""
        client = await self.redisService.client()
        payload = [{"queryVector": queryVector, "content": item.chunk.content, "chunkId": item.chunk.chunkId, "headingPath": item.chunk.headingPath, "pageNumber": item.chunk.pageNumber} for item in results]
        await client.set(f"agent:rag:session:{sessionId}:{scopeKey}:results", json.dumps(payload, ensure_ascii=False), ex=self.ttlSeconds)

    async def clear(self, sessionId: str) -> None:
        """面试结束时清理会话缓存。"""
        client = await self.redisService.client()
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=f"agent:rag:session:{sessionId}:*:results", count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                return

    def cosine(self, left: list[float], right: list[float]) -> float:
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0
