from typing import Any
from pathlib import Path

from agent.Common.Configs.settings import AgentSettings
from agent.Common.Exceptions.agent_exception import AgentInfrastructureUnavailableError


class PostgresService:
    """以惰性方式管理 Agent PostgreSQL 连接池，避免导入阶段建立外部连接。"""

    def __init__(self, settings: AgentSettings) -> None:
        """保存配置并延迟创建连接池，供记忆仓储等基础设施使用。"""
        self.settings = settings
        self.pool: Any | None = None

    async def getPool(self) -> Any:
        """在首次数据库操作时创建 asyncpg 连接池，并将依赖缺失转换为领域异常。"""
        if self.pool is not None:
            return self.pool

        try:
            import asyncpg
        except ImportError as error:
            raise AgentInfrastructureUnavailableError(
                "缺少 asyncpg 依赖，无法访问 Agent PostgreSQL",
            ) from error

        self.pool = await asyncpg.create_pool(self.settings.requirePostgresUrl())
        return self.pool

    async def close(self) -> None:
        """在 Agent 服务关闭时释放数据库连接池。"""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def runMemoryMigrations(self) -> None:
        """按文件顺序执行记忆与工作流迁移，确保新增能力可以在已有数据库上平滑升级。"""
        migrationDirectory = Path(__file__).resolve().parents[2] / "Memory" / "migrations"
        pool = await self.getPool()
        async with pool.acquire() as connection:
            for migrationPath in sorted(migrationDirectory.glob("*.sql")):
                await connection.execute(migrationPath.read_text(encoding="utf-8"))

    async def runRagMigrations(self) -> None:
        """执行 RAG 表结构迁移，创建 pgvector、chunk 和全文检索索引。"""
        migrationDirectory = Path(__file__).resolve().parents[2] / "RAG" / "migrations"
        pool = await self.getPool()
        async with pool.acquire() as connection:
            for migrationPath in sorted(migrationDirectory.glob("*.sql")):
                await connection.execute(migrationPath.read_text(encoding="utf-8"))
