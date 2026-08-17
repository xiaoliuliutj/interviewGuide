from dataclasses import dataclass, field
from typing import Any, Literal

from agent.Common.AgentRequest import AgentOperationRequest
from agent.Common.AgentResults import AgentTaskType


@dataclass(frozen=True)
class AgentMessage:
    """表示一次发送给大语言模型的上下文消息。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None


@dataclass(frozen=True)
class ToolCall:
    """表示模型请求执行的受限工具及其参数。"""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolExecutionResult:
    """表示工具执行后返回给 AgentLoop 的结果。"""

    name: str
    content: str
    succeeded: bool


@dataclass(frozen=True)
class LlmResponse:
    """表示模型一次调用产生的最终数据或工具调用。"""

    finalData: dict[str, Any] | None = None
    toolCall: ToolCall | None = None


@dataclass(frozen=True)
class SkillDefinition:
    """表示当前 AgentLoop 使用的系统提示词和允许的工具范围。"""

    taskType: AgentTaskType
    systemPrompt: str
    allowedToolNames: tuple[str, ...] = ()
    memoryEnabled: bool = False
    ragEnabled: bool = False
    allowedSystemKnowledgeBaseIds: tuple[str, ...] | None = None


@dataclass
class AgentContext:
    """保存一。"AgentLoop 运行期间共享的请求、Skill 与消息上下文。"""

    request: AgentOperationRequest
    skill: SkillDefinition
    messages: list[AgentMessage] = field(default_factory=list)
    stepCount: int = 0
    redisLeaseEnabled: bool = True


@dataclass(frozen=True)
class AgentLoopCommand:
    """封装经过 API 校验后交。"AgentLoop 的运行参数。"""

    request: AgentOperationRequest
    parsedPayload: dict[str, Any]
