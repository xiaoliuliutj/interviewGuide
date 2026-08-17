from dataclasses import dataclass, field
from typing import Any, Literal

from agent.Common.results import AgentTaskType
from agent.api.contracts import AgentOperationRequest


@dataclass(frozen=True)
class AgentMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    content: str
    succeeded: bool


@dataclass(frozen=True)
class LlmResponse:
    finalData: dict[str, Any] | None = None
    toolCall: ToolCall | None = None


@dataclass(frozen=True)
class SkillDefinition:
    taskType: AgentTaskType
    systemPrompt: str
    allowedToolNames: tuple[str, ...] = ()
    memoryEnabled: bool = False
    ragEnabled: bool = False
    allowedSystemKnowledgeBaseIds: tuple[str, ...] | None = None


@dataclass
class AgentContext:
    request: AgentOperationRequest
    skill: SkillDefinition
    messages: list[AgentMessage] = field(default_factory=list)
    stepCount: int = 0
    redisLeaseEnabled: bool = True


@dataclass(frozen=True)
class AgentLoopCommand:
    request: AgentOperationRequest
    parsedPayload: dict[str, Any]
