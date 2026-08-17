from agent.Common.results import AgentResultStatus


class AgentException(Exception):
    """Base exception for errors raised inside the Python Agent layer."""

    def __init__(
        self,
        message: str,
        status_code: AgentResultStatus = AgentResultStatus.AGENT_EXECUTION_FAILED,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class _FixedStatusAgentException(AgentException):
    status_code: AgentResultStatus
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message, self.status_code, retryable=self.retryable)


class AgentConfigurationError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_CONFIGURATION_INVALID


class AgentRequestContractError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_REQUEST_CONTRACT_INVALID


class AgentTaskUnsupportedError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_TASK_UNSUPPORTED


class AgentInfrastructureUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_SERVICE_UNAVAILABLE
    retryable = True


class LlmProviderUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_PROVIDER_UNAVAILABLE
    retryable = True


class LlmAuthenticationError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_AUTHENTICATION_FAILED


class LlmRateLimitError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_RATE_LIMITED
    retryable = True


class LlmTimeoutError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_REQUEST_TIMEOUT
    retryable = True


class LlmEmptyResponseError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_EMPTY_RESPONSE
    retryable = True


class LlmToolCallMalformedError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_TOOL_CALL_MALFORMED


class LlmOutputSchemaError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_OUTPUT_SCHEMA_INVALID


class LlmContentRejectedError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_CONTENT_REJECTED


class LlmContextLimitExceededError(_FixedStatusAgentException):
    status_code = AgentResultStatus.LLM_CONTEXT_LIMIT_EXCEEDED


class ToolNotRegisteredError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_NOT_REGISTERED


class ToolNotAuthorizedError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_NOT_AUTHORIZED


class ToolArgumentError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_ARGUMENT_INVALID


class ToolTimeoutError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_EXECUTION_TIMEOUT
    retryable = True


class ToolExecutionError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_EXECUTION_FAILED


class ToolResultValidationError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_RESULT_INVALID


class ToolDependencyUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.TOOL_DEPENDENCY_UNAVAILABLE
    retryable = True


class MemoryUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.MEMORY_SERVICE_UNAVAILABLE
    retryable = True


class MemoryReadError(_FixedStatusAgentException):
    status_code = AgentResultStatus.MEMORY_READ_FAILED
    retryable = True


class MemoryWriteError(_FixedStatusAgentException):
    status_code = AgentResultStatus.MEMORY_WRITE_FAILED
    retryable = True


class MemorySerializationError(_FixedStatusAgentException):
    status_code = AgentResultStatus.MEMORY_SERIALIZATION_FAILED


class MemoryVersionConflictError(_FixedStatusAgentException):
    status_code = AgentResultStatus.MEMORY_VERSION_CONFLICT
    retryable = True


class MemoryLockUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.MEMORY_LOCK_UNAVAILABLE
    retryable = True


class RagUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_SERVICE_UNAVAILABLE
    retryable = True


class RagRetrievalError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_RETRIEVAL_FAILED
    retryable = True


class RagEmbeddingError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_EMBEDDING_FAILED
    retryable = True


class RagVectorStoreError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_VECTOR_STORE_FAILED
    retryable = True


class RagIndexingError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_INDEXING_FAILED
    retryable = True


class RagDeletionError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_DELETION_FAILED
    retryable = True


class RagDocumentParseError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_DOCUMENT_PARSE_FAILED


class RagDocumentTooLargeError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RAG_DOCUMENT_TOO_LARGE


class RedisUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.REDIS_UNAVAILABLE
    retryable = True


class RedisTimeoutError(_FixedStatusAgentException):
    status_code = AgentResultStatus.REDIS_OPERATION_TIMEOUT
    retryable = True


class RabbitMqUnavailableError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RABBITMQ_UNAVAILABLE
    retryable = True


class RabbitMqPublishError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RABBITMQ_PUBLISH_FAILED
    retryable = True


class RabbitMqConsumeError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RABBITMQ_CONSUME_FAILED
    retryable = True


class RabbitMqMessageError(_FixedStatusAgentException):
    status_code = AgentResultStatus.RABBITMQ_MESSAGE_INVALID


class AgentSessionNotFoundError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_SESSION_NOT_FOUND


class AgentSessionConcurrencyError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_SESSION_CONCURRENCY_CONFLICT
    retryable = True


class AgentSessionStateError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_SESSION_STATE_INVALID


class AgentStatePersistenceError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_STATE_PERSISTENCE_FAILED
    retryable = True


class AgentRunCancelledError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_RUN_CANCELLED


class AgentRunStepLimitError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_RUN_STEP_LIMIT_EXCEEDED


class AgentRunDeadlineError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_RUN_DEADLINE_EXCEEDED
    retryable = True


class PromptNotFoundError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_PROMPT_NOT_FOUND


class SkillNotFoundError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_SKILL_NOT_FOUND


class SkillConfigurationError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_SKILL_CONFIGURATION_INVALID


class ExternalWebRequestError(_FixedStatusAgentException):
    status_code = AgentResultStatus.EXTERNAL_WEB_REQUEST_FAILED
    retryable = True


class ExternalWebContentUnsafeError(_FixedStatusAgentException):
    status_code = AgentResultStatus.EXTERNAL_WEB_CONTENT_UNSAFE


class AgentInternalError(_FixedStatusAgentException):
    status_code = AgentResultStatus.AGENT_INTERNAL_ERROR
