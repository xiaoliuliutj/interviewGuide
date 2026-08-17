from typing import Any

from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Exceptions.AgentException import RedisUnavailableError


class RedisService:
    """Shared Redis adapter for Agent session state, locks and short-lived data."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._client: Any | None = None

    async def client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            import redis.asyncio as redis
        except ImportError as error:
            raise RedisUnavailableError(
                "Redis support requires the redis package",
            ) from error

        self._client = redis.from_url(
            self._settings.require_redis_url(),
            decode_responses=True,
        )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
