"""将指。"Agent 知识库标记为系统知识库。"""

import argparse
import asyncio

from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Postgres.PostgresService import PostgresService


async def markSystemKnowledgeBase(knowledgeBaseId: str) -> None:
    """校验目标存在且已就绪后，将其切换。"SYSTEM，后续由 Skill 白名单控制检索范围。"""
    postgresService = PostgresService(AgentSettings.from_environment())
    try:
        pool = await postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE rag_knowledge_bases SET knowledge_base_type='SYSTEM' WHERE knowledge_base_id=$1 AND status='READY' RETURNING knowledge_base_id",
                knowledgeBaseId,
            )
        if updated is None:
            raise SystemExit("知识库不存在或尚未 READY，无法设为系统知识库")
    finally:
        await postgresService.close()


def parseArguments() -> argparse.Namespace:
    """读取唯一必填的知识库标识，避免脚本误操作多个知识库。"""
    parser = argparse.ArgumentParser(description="标记系统知识库")
    parser.add_argument("knowledgeBaseId")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parseArguments()
    asyncio.run(markSystemKnowledgeBase(arguments.knowledgeBaseId))
