from typing import Any
import json

from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Exceptions.AgentException import RabbitMqUnavailableError


class RabbitMqService:
    """Shared RabbitMQ adapter for background Agent task messages."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._connection: Any | None = None

    async def connection(self) -> Any:
        if self._connection is not None:
            return self._connection

        try:
            import aio_pika
        except ImportError as error:
            raise RabbitMqUnavailableError(
                "RabbitMQ support requires the aio-pika package",
            ) from error

        self._connection = await aio_pika.connect_robust(
            self._settings.require_rabbitmq_url(),
        )
        return self._connection

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def publishEvent(self, eventType: str, payload: dict[str, Any]) -> None:
        """发布持久化 Outbox 事件，消息体携带类型以便消费者按业务路由。"""
        try:
            import aio_pika
        except ImportError as error:
            raise RabbitMqUnavailableError("缺少 aio-pika 依赖，无法发布 Outbox 事件") from error
        connection = await self.connection()
        channel = await connection.channel()
        try:
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(
                        {"eventType": eventType, "payload": payload},
                        ensure_ascii=False,
                    ).encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="agent.memory.events",
            )
        finally:
            await channel.close()

    async def consumeEvents(self, handler) -> None:
        """声明持久化队列并把消息交给业务处理器，处理成功后才确认消息。"""
        connection = await self.connection()
        channel = await connection.channel()
        await channel.declare_queue("agent.memory.events.dlq", durable=True)
        queue = await channel.declare_queue(
            "agent.memory.events",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "agent.memory.events.dlq",
            },
        )

        async def process(message) -> None:
            # 摘要失败会由业务逻辑重新写入 Outbox；格式错误等毒消息进入死信队列，
            # 不在主队列无限重试而阻塞后续事件。
            async with message.process(requeue=False):
                await handler(json.loads(message.body.decode("utf-8")))

        await queue.consume(process)
