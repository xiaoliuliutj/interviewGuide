from typing import Any

from agent.LLM.llmService import LlmService
from agent.RAG.ragRuntime import RagRuntime


class RagService:
    """。"AgentLoop 提供 RAG 领域服务入口。"""

    def __init__(self, llmService: LlmService | None = None) -> None:
        """组装 RagRuntime，服务入口本身只负责暴露领域能力。"""
        self.runtime = RagRuntime(llmService)

    def __getattr__(self, name: str) -> Any:
        """将已注册。"RAG 能力转交给领域运行时。"""
        return getattr(self.runtime, name)
