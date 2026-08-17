import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from agent.Common.Exceptions.agent_exception import AgentConfigurationError


# 本地启动读取 agent/.env；Docker Compose 会通过环境变量注入，重复加载不会覆盖外部环境。
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


@dataclass(frozen=True)
class AgentSettings:
    """Configuration shared by Agent API, workers and infrastructure adapters."""

    redis_url: str | None
    rabbitmq_url: str | None
    postgres_url: str | None
    openai_base_url: str | None
    openai_model: str | None
    openai_api_key: str | None
    embedding_base_url: str | None
    embedding_model: str | None
    embedding_api_key: str | None
    embedding_dimensions: int

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        return cls(
            redis_url=os.getenv("INTERVIEW_GUIDE_REDIS_URL"),
            rabbitmq_url=os.getenv("INTERVIEW_GUIDE_RABBITMQ_URL"),
            postgres_url=os.getenv("INTERVIEW_GUIDE_POSTGRES_URL"),
            openai_base_url=os.getenv("INTERVIEW_GUIDE_OPENAI_BASE_URL"),
            openai_model=os.getenv("INTERVIEW_GUIDE_OPENAI_MODEL"),
            openai_api_key=os.getenv("INTERVIEW_GUIDE_OPENAI_API_KEY"),
            embedding_base_url=os.getenv("INTERVIEW_GUIDE_EMBEDDING_BASE_URL"),
            embedding_model=os.getenv("INTERVIEW_GUIDE_EMBEDDING_MODEL"),
            embedding_api_key=os.getenv("INTERVIEW_GUIDE_EMBEDDING_API_KEY"),
            embedding_dimensions=int(os.getenv("INTERVIEW_GUIDE_EMBEDDING_DIMENSIONS", "1536")),
        )

    def require_redis_url(self) -> str:
        if not self.redis_url:
            raise AgentConfigurationError(
                "INTERVIEW_GUIDE_REDIS_URL is required to use Redis",
            )
        return self.redis_url

    def require_rabbitmq_url(self) -> str:
        if not self.rabbitmq_url:
            raise AgentConfigurationError(
                "INTERVIEW_GUIDE_RABBITMQ_URL is required to use RabbitMQ",
            )
        return self.rabbitmq_url

    def requirePostgresUrl(self) -> str:
        """返回 Agent PostgreSQL 连接地址，未配置时阻止持久化操作。"""
        if not self.postgres_url:
            raise AgentConfigurationError(
                "缺少 INTERVIEW_GUIDE_POSTGRES_URL，无法访问 Agent PostgreSQL",
            )
        return self.postgres_url

    def requireOpenAiConfiguration(self) -> tuple[str, str, str]:
        """返回 OpenAI SDK 必需配置，避免模型调用在运行中因缺少密钥失败。"""
        if not self.openai_base_url or not self.openai_model or not self.openai_api_key:
            raise AgentConfigurationError("缺少 OpenAI 的 URL、模型名称或 API Key 配置")
        return self.openai_base_url, self.openai_model, self.openai_api_key

    def requireEmbeddingConfiguration(self) -> tuple[str, str, str, int]:
        """返回 embedding 服务配置，避免向量化逻辑依赖对话模型配置。"""
        if not self.embedding_base_url or not self.embedding_model or not self.embedding_api_key:
            raise AgentConfigurationError("缺少 embedding 的 URL、模型名或 API Key 配置")
        if self.embedding_dimensions < 1:
            raise AgentConfigurationError("embedding 向量维度必须大于 0")
        return (
            self.embedding_base_url,
            self.embedding_model,
            self.embedding_api_key,
            self.embedding_dimensions,
        )
