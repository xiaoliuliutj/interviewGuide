from agent.Common.RabbitMQ.RabbitMqService import RabbitMqService
from agent.Memory.memoryRepository import MemoryRepository


class MemoryOutboxPublisher:
    """将数据库已提交的记忆事件可靠发布到 RabbitMQ，避免数据库与消息系统直接双写。"""

    def __init__(self, repository: MemoryRepository, rabbitMqService: RabbitMqService) -> None:
        """注入 Outbox 仓储与 RabbitMQ 服务，发布失败时不改变数据库事件状态。"""
        self.repository = repository
        self.rabbitMqService = rabbitMqService

    async def publishPendingEvents(self) -> int:
        """扫描并发布待处理事件；单条发布失败会停止本批次，保留剩余事件等待重试。"""
        published = 0
        for event in await self.repository.loadPendingEvents():
            try:
                await self.rabbitMqService.publishEvent(
                    event["event_type"],
                    {"eventId": str(event["event_id"]), "aggregateId": event["aggregate_id"], "data": event["payload"]},
                )
                await self.repository.markEventPublished(event["event_id"])
                published += 1
            except Exception:
                await self.repository.resetEventPending(event["event_id"])
                raise
        return published
