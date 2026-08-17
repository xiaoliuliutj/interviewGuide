from agent.Memory.memory_service import MemoryService


class MemoryEventWorker:
    """消费记忆后台事件，负责摘要失败后的异步补偿。"""

    def __init__(self, memoryService: MemoryService) -> None:
        """注入记忆服务，消费者只负责路由事件而不重复实现摘要逻辑。"""
        self.memoryService = memoryService

    async def close(self) -> None:
        """释放后台消费者独立持有的记忆基础设施连接。"""
        await self.memoryService.close()

    async def handleEvent(self, event: dict) -> None:
        """处理摘要重试事件，未知事件直接拒绝以防错误消息被静默吞掉。"""
        if event.get("eventType") != "SESSION_SUMMARY_RETRY":
            raise ValueError(f"不支持的记忆事件：{event.get('eventType')}")
        sessionId = str(event["payload"]["aggregateId"])
        await self.memoryService.retrySummary(sessionId)
