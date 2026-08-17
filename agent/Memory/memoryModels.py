from dataclasses import dataclass

from agent.Common.AgentModels import AgentMessage


@dataclass(frozen=True)
class SessionMemorySnapshot:
    """表示可重建的会话短期记忆快照，包含滚动摘要与最近原始对话。"""

    stateVersion: int
    rollingSummary: str | None
    messages: list[AgentMessage]
    summarizedUntilSequence: int = 0


@dataclass(frozen=True)
class LongTermMemorySnapshot:
    """表示当前任务可注入的长期记忆，不保存原始敏感简历文本。"""

    userProfile: str | None
    resumeMemory: str | None
    interviewOverview: str | None
