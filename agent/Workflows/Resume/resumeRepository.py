"""简历原文、异步任务和评估结果的 PostgreSQL 持久化。"""

import json
from typing import Any
from uuid import uuid4

from agent.Common.Exceptions.AgentException import AgentSessionStateError
from agent.Common.Postgres.PostgresService import PostgresService
from agent.WorkFlows.Resume.resumeModels import ResumeEvaluation, ResumeJobStatus


class ResumeWorkflowRepository:
    """封装简历任务的幂等上传、领取、重试和结果查询。"""

    def __init__(self, postgresService: PostgresService) -> None:
        """保存统一 PostgreSQL 连接池服务。"""
        self.postgresService = postgresService

    async def saveUpload(
        self,
        resumeId: str,
        userId: str,
        fileName: str,
        contentType: str | None,
        content: bytes,
        targetRole: str | None,
        runId: str,
        conversationId: str,
    ) -> dict[str, object]:
        """保存原文并创建幂等异步任务，重复 runId 直接返回已有任务。"""
        import hashlib

        contentHash = hashlib.sha256(content).hexdigest()
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT status,resume_id FROM agent_resume_job WHERE run_id=$1",
                    runId,
                )
                if existing is not None:
                    return {"resumeId": existing["resume_id"], "status": existing["status"], "runId": runId}
                owner = await connection.fetchval(
                    "SELECT user_id FROM agent_resume_document WHERE resume_id=$1",
                    resumeId,
                )
                if owner is not None and owner != userId:
                    raise AgentSessionStateError("简历不属于当前调用主体")
                await connection.execute(
                    "INSERT INTO agent_resume_document(resume_id,user_id,file_name,content_type,raw_content,content_hash,target_role,status) "
                    "VALUES($1,$2,$3,$4,$5,$6,$7,'UPLOADED') "
                    "ON CONFLICT(resume_id) DO UPDATE SET user_id=EXCLUDED.user_id,file_name=EXCLUDED.file_name,content_type=EXCLUDED.content_type,"
                    "raw_content=EXCLUDED.raw_content,extracted_text=NULL,content_hash=EXCLUDED.content_hash,target_role=EXCLUDED.target_role,"
                    "status='UPLOADED',evaluation_json=NULL,error_message=NULL,updated_at=CURRENT_TIMESTAMP",
                    resumeId,
                    userId,
                    fileName,
                    contentType,
                    content,
                    contentHash,
                    targetRole,
                )
                await connection.execute(
                    "INSERT INTO agent_resume_job(job_id,run_id,resume_id,user_id,conversation_id,target_role,status) "
                    "VALUES($1,$2,$3,$4,$5,$6,'PENDING')",
                    uuid4(),
                    runId,
                    resumeId,
                    userId,
                    conversationId,
                    targetRole,
                )
        return {"resumeId": resumeId, "status": ResumeJobStatus.PENDING.value, "runId": runId}

    async def findLatest(self, userId: str) -> dict[str, object] | None:
        """返回用户最近上传的简历元数据，支持自然语言请求省略 resumeId。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT resume_id,status,target_role,evaluation_json,updated_at FROM agent_resume_document "
                "WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
                userId,
            )
        return dict(row) if row else None

    async def loadDocument(self, resumeId: str, userId: str) -> dict[str, object] | None:
        """读取归属校验后的原始简历，供后台解析器执行确定性文本提取。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT resume_id,file_name,content_type,raw_content,target_role FROM agent_resume_document WHERE resume_id=$1 AND user_id=$2",
                resumeId,
                userId,
            )
        return dict(row) if row else None

    async def claimJobs(self, limit: int = 5) -> list[dict[str, object]]:
        """使用 SKIP LOCKED 领取待处理任务，使多实例 worker 可以安全并行。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    "SELECT job_id,run_id,resume_id,user_id,conversation_id,target_role,attempt_count FROM agent_resume_job "
                    "WHERE status='PENDING' ORDER BY created_at LIMIT $1 FOR UPDATE SKIP LOCKED",
                    limit,
                )
                for row in rows:
                    await connection.execute(
                        "UPDATE agent_resume_job SET status='PROCESSING',attempt_count=attempt_count+1,started_at=CURRENT_TIMESTAMP WHERE job_id=$1",
                        row["job_id"],
                    )
                    await connection.execute(
                        "UPDATE agent_resume_document SET status='PARSING',updated_at=CURRENT_TIMESTAMP WHERE resume_id=$1",
                        row["resume_id"],
                    )
        return [dict(row) for row in rows]

    async def markAnalyzing(self, resumeId: str, text: str) -> None:
        """保存解析后的纯文本，再将任务推进到 LLM 分析阶段。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_resume_document SET extracted_text=$2,status='ANALYZING',updated_at=CURRENT_TIMESTAMP WHERE resume_id=$1",
                resumeId,
                text,
            )

    async def completeJob(self, runId: str, resumeId: str, evaluation: ResumeEvaluation) -> None:
        """在同一事务中保存评估 JSON 并将任务标记完成，供长期记忆随后读取。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE agent_resume_document SET status='COMPLETED',evaluation_json=$2::jsonb,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE resume_id=$1",
                    resumeId,
                    json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False),
                )
                await connection.execute(
                    "UPDATE agent_resume_job SET status='COMPLETED',completed_at=CURRENT_TIMESTAMP,error_message=NULL WHERE run_id=$1",
                    runId,
                )

    async def failJob(self, runId: str, resumeId: str, errorMessage: str, final: bool) -> None:
        """失败时按最大重试策略回到 PENDING 或进入最终失败，避免静默丢失任务。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE agent_resume_document SET status=$3,error_message=$2,updated_at=CURRENT_TIMESTAMP WHERE resume_id=$1",
                resumeId,
                errorMessage,
                "FAILED" if final else "ANALYZING",
            )
            await connection.execute(
                "UPDATE agent_resume_job SET status=$2,error_message=$3,completed_at=CASE WHEN $2='FAILED_FINAL' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE run_id=$1",
                runId,
                "FAILED_FINAL" if final else "PENDING",
                errorMessage,
            )

    async def loadJob(self, runId: str, userId: str) -> dict[str, object] | None:
        """查询任务状态并强制校验主体归属，支持 Java 轮询或自然语言再次查询。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT j.run_id,j.resume_id,j.status AS job_status,j.attempt_count,j.error_message,d.status,d.evaluation_json "
                "FROM agent_resume_job j JOIN agent_resume_document d ON d.resume_id=j.resume_id "
                "WHERE j.run_id=$1 AND j.user_id=$2",
                runId,
                userId,
            )
        return dict(row) if row else None

    async def loadLatestEvaluation(self, userId: str, resumeId: str | None) -> dict[str, object] | None:
        """读取最新评估结果，供自然语言的“分析简历”请求直接返回已完成结果。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT resume_id,status,evaluation_json,error_message FROM agent_resume_document "
                "WHERE user_id=$1 AND ($2::text IS NULL OR resume_id=$2) ORDER BY updated_at DESC LIMIT 1",
                userId,
                resumeId,
            )
        return dict(row) if row else None

    async def recreateJob(self, resumeId: str, userId: str, targetRole: str, runId: str, conversationId: str) -> dict[str, object]:
        """基于已有原文创建新的幂等分析任务，避免 Java 重传或读取正文。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT resume_id,status FROM agent_resume_job WHERE run_id=$1", runId
                )
                if existing is not None:
                    return {"resumeId": existing["resume_id"], "status": existing["status"], "runId": runId}
                document = await connection.fetchrow(
                    "SELECT 1 FROM agent_resume_document WHERE resume_id=$1 AND user_id=$2", resumeId, userId
                )
                if document is None:
                    raise AgentSessionStateError("简历不存在或不属于当前用户")
                await connection.execute(
                    "UPDATE agent_resume_document SET target_role=$3,status='UPLOADED',evaluation_json=NULL,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE resume_id=$1 AND user_id=$2",
                    resumeId, userId, targetRole
                )
                await connection.execute(
                    "INSERT INTO agent_resume_job(job_id,run_id,resume_id,user_id,conversation_id,target_role,status) VALUES($1,$2,$3,$4,$5,$6,'PENDING')",
                    uuid4(), runId, resumeId, userId, conversationId, targetRole
                )
        return {"resumeId": resumeId, "status": ResumeJobStatus.PENDING.value, "runId": runId}

    async def downloadDocument(self, resumeId: str, userId: str) -> dict[str, object] | None:
        """读取归属校验后的原始简历，供 API 进行 Base64 跨服务传输。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT file_name,content_type,raw_content FROM agent_resume_document WHERE resume_id=$1 AND user_id=$2",
                resumeId, userId
            )
        return dict(row) if row else None

    async def deleteResume(self, resumeId: str, userId: str) -> bool:
        """原子删除简历任务、原文与对应长期记忆；重复删除视为成功。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("DELETE FROM agent_resume_job WHERE resume_id=$1 AND user_id=$2", resumeId, userId)
                await connection.execute("UPDATE agent_resume_memory SET deleted_at=CURRENT_TIMESTAMP,is_current=FALSE WHERE resume_id=$1 AND user_id=$2 AND deleted_at IS NULL", resumeId, userId)
                result = await connection.execute("DELETE FROM agent_resume_document WHERE resume_id=$1 AND user_id=$2", resumeId, userId)
        return result != "DELETE 0"
