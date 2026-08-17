from typing import Any

from agent.LLM.llmService import LlmService
from agent.Memory.memoryRuntime import MemoryRuntime


class MemoryService:
    """。"AgentLoop 提供 Memory 领域服务入口。"""

    def __init__(self, llmService: LlmService | None = None) -> None:
        """组装 MemoryRuntime，服务入口本身只负责暴露领域能力。"""
        self.runtime = MemoryRuntime(llmService)

    def __getattr__(self, name: str) -> Any:
        """将已注册。"Memory 能力转交给领域运行时。"""
        return getattr(self.runtime, name)
