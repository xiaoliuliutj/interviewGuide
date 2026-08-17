import math
import re
import json
from uuid import uuid4
from typing import Any

from agent.Common.Exceptions.AgentException import RagRetrievalError, RagVectorStoreError
from agent.Common.Postgres.PostgresService import PostgresService
from agent.RAG.ragModels import DocumentChunk, RagAccessScope, RagSearchResult


class RagRepository:
    """PostgreSQL/pgvector 持久化适配器；正文和向量只存在 Agent 数据库。"""

    def __init__(self, postgresService: PostgresService) -> None:
        self.postgresService = postgresService

    async def ensureKnowledgeBase(self, knowledgeBaseId: str, ownerUserId: str) -> int:
        """幂等创建知识库状态记录，索引完成前保持 BUILDING。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            existing = await connection.fetchrow(
                "SELECT owner_user_id,status FROM rag_knowledge_bases WHERE knowledge_base_id=$1 FOR UPDATE",
                knowledgeBaseId,
            )
            existingOwner = existing["owner_user_id"] if existing is not None else None
            if existingOwner is not None and existingOwner != ownerUserId:
                raise RagRetrievalError("知识库不属于当前用户，拒绝覆盖索引")
            if existing is not None and existing["status"] in {"DELETE_REQUESTED", "DELETED"}:
                raise RagRetrievalError("知识库已进入删除流程，不能重新建立索引")
            version = await connection.fetchval(
                "INSERT INTO rag_knowledge_bases(knowledge_base_id,owner_user_id,status,index_version) VALUES($1,$2,'BUILDING',1) ON CONFLICT (knowledge_base_id) DO UPDATE SET status='BUILDING',index_version=rag_knowledge_bases.index_version+1 RETURNING index_version",
                knowledgeBaseId,
                ownerUserId,
            )
        return int(version)

    async def loadCompletedIndexRun(self, knowledgeBaseId: str, runId: str) -> dict[str, object] | None:
        """读取已完成的同一索引 run，避免网络重试重复切分和调用 embedding。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT last_document_id,last_chunk_count FROM rag_knowledge_bases WHERE knowledge_base_id=$1 AND last_index_run_id=$2 AND status='READY'",
                knowledgeBaseId,
                runId,
            )
        if row is None:
            return None
        return {"documentId": row["last_document_id"], "chunkCount": row["last_chunk_count"]}

    async def completeIndexRun(self, knowledgeBaseId: str, documentId: str, runId: str, indexVersion: int, chunkCount: int) -> None:
        """原子记录索引完成结果，使同 runId 的重试可以直接重放成功响应。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE rag_knowledge_bases SET status='READY',last_index_run_id=$2,last_document_id=$3,last_chunk_count=$5 WHERE knowledge_base_id=$1 AND status='BUILDING' AND index_version=$4 RETURNING knowledge_base_id",
                knowledgeBaseId,
                runId,
                documentId,
                indexVersion,
                chunkCount,
            )
        if updated is None:
            raise RagVectorStoreError("知识库已进入删除流程，拒绝提交索引完成状态")

    async def createIndexJob(self, runId: str, knowledgeBaseId: str, documentId: str, userId: str, indexVersion: int) -> dict[str, object]:
        """持久化索引任务；相同 runId 重试只返回已有任务，不重复创建。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT status FROM rag_index_job WHERE run_id=$1", runId)
            if row is None:
                await connection.execute(
                    "UPDATE rag_index_job SET status='FAILED_FINAL',error_message='被新索引版本替代',updated_at=CURRENT_TIMESTAMP WHERE knowledge_base_id=$1 AND status IN ('PENDING','PROCESSING','FAILED') AND index_version < $2",
                    knowledgeBaseId,
                    indexVersion,
                )
                await connection.execute(
                    "INSERT INTO rag_index_job(job_id,run_id,knowledge_base_id,document_id,user_id,index_version,status) VALUES($1,$2,$3,$4,$5,$6,'PENDING')",
                    uuid4().hex,
                    runId,
                    knowledgeBaseId,
                    documentId,
                    userId,
                    indexVersion,
                )
                return {"status": "PENDING"}
        return {"status": row["status"]}

    async def findIndexJob(self, runId: str) -> dict[str, object] | None:
        """查询同一 run 是否已经完成暂存，供网络重试直接重放状态。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT status,knowledge_base_id,document_id,user_id,index_version FROM rag_index_job WHERE run_id=$1", runId)
        return dict(row) if row is not None else None

    async def claimIndexJobs(self) -> list[dict[str, object]]:
        """领取待处理或租约超时的索引任务，进程崩溃后可由其他实例恢复。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "UPDATE rag_index_job SET status='PROCESSING',claimed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE job_id IN (SELECT job_id FROM rag_index_job WHERE ((status IN ('PENDING','FAILED') AND next_attempt_at<=CURRENT_TIMESTAMP) OR (status='PROCESSING' AND claimed_at<CURRENT_TIMESTAMP-INTERVAL '5 minutes')) AND attempt_count<3 FOR UPDATE SKIP LOCKED) RETURNING job_id,run_id,knowledge_base_id,document_id,user_id,index_version",
            )
        return [dict(row) for row in rows]

    async def loadIndexDocument(self, documentId: str) -> dict[str, object]:
        """由后台 worker 读取已暂存的原文件，不依赖 Java 保留正文。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT knowledge_base_id,file_name,content_type,original_content FROM rag_documents WHERE document_id=$1", documentId)
        if row is None:
            raise RagVectorStoreError("索引任务对应的原始文件不存在")
        return {"knowledgeBaseId": row["knowledge_base_id"], "fileName": row["file_name"], "contentType": row["content_type"], "content": bytes(row["original_content"])}

    async def getIndexVersion(self, knowledgeBaseId: str) -> int:
        """读取当前构建版本，使后台写入的 chunk 与知识库版本一致。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            version = await connection.fetchval("SELECT index_version FROM rag_knowledge_bases WHERE knowledge_base_id=$1", knowledgeBaseId)
        if version is None:
            raise RagVectorStoreError("知识库不存在")
        return int(version)

    async def isIndexingAllowed(self, knowledgeBaseId: str, indexVersion: int) -> bool:
        """在后台写入前再次检查生命周期，防止删除与索引并发恢复出已删除内容。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            status = await connection.fetchval(
                "SELECT status FROM rag_knowledge_bases WHERE knowledge_base_id=$1 AND index_version=$2 FOR UPDATE",
                knowledgeBaseId,
                indexVersion,
            )
        return status == "BUILDING"

    async def resumeIndexing(self, knowledgeBaseId: str, indexVersion: int) -> bool:
        """仅恢复当前索引版本的失败任务，禁止旧任务或删除中的知识库复活。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE rag_knowledge_bases SET status='BUILDING' WHERE knowledge_base_id=$1 AND index_version=$2 AND status='FAILED' RETURNING knowledge_base_id",
                knowledgeBaseId,
                indexVersion,
            )
        return updated is not None

    async def setKnowledgeBaseStatusIfVersion(
        self,
        knowledgeBaseId: str,
        indexVersion: int,
        status: str,
    ) -> bool:
        """只更新仍属于指定索引版本的知识库，防止旧 worker 覆盖新状态。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE rag_knowledge_bases SET status=$3 WHERE knowledge_base_id=$1 AND index_version=$2 AND status NOT IN ('DELETE_REQUESTED','DELETED') RETURNING knowledge_base_id",
                knowledgeBaseId,
                indexVersion,
                status,
            )
        return updated is not None

    async def acquireRetrievalLease(
        self,
        leaseId: str,
        knowledgeBaseIds: list[str],
        ttlSeconds: int = 120,
    ) -> bool:
        """在数据库事务中确认 READY 并登记检索租约，阻止删除与新检索竞态。"""
        if not knowledgeBaseIds:
            return False
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM rag_retrieval_lease WHERE expires_at <= CURRENT_TIMESTAMP",
                )
                rows = await connection.fetch(
                    "SELECT knowledge_base_id FROM rag_knowledge_bases WHERE knowledge_base_id=ANY($1) AND status='READY' FOR UPDATE",
                    knowledgeBaseIds,
                )
                if len(rows) != len(set(knowledgeBaseIds)):
                    return False
                await connection.executemany(
                    "INSERT INTO rag_retrieval_lease(lease_id,knowledge_base_id,expires_at) VALUES($1,$2,CURRENT_TIMESTAMP + ($3 * INTERVAL '1 second')) ON CONFLICT DO NOTHING",
                    [(leaseId, knowledgeBaseId, ttlSeconds) for knowledgeBaseId in set(knowledgeBaseIds)],
                )
        return True

    async def releaseRetrievalLease(self, leaseId: str) -> None:
        """释放一次检索对知识库的引用。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM rag_retrieval_lease WHERE lease_id=$1",
                leaseId,
            )

    async def countActiveRetrievalLeases(self, knowledgeBaseId: str) -> int:
        """清理过期租约并返回当前知识库仍被检索引用的数量。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM rag_retrieval_lease WHERE expires_at <= CURRENT_TIMESTAMP",
            )
            count = await connection.fetchval(
                "SELECT COUNT(*) FROM rag_retrieval_lease WHERE knowledge_base_id=$1",
                knowledgeBaseId,
            )
        return int(count or 0)

    async def finishIndexJob(self, jobId: str, succeeded: bool, errorMessage: str | None = None) -> None:
        """提交后台索引结果；失败任务保留并按固定间隔恢复。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            if succeeded:
                await connection.execute("UPDATE rag_index_job SET status='COMPLETED',updated_at=CURRENT_TIMESTAMP WHERE job_id=$1", jobId)
            else:
                await connection.execute("UPDATE rag_index_job SET status=CASE WHEN attempt_count + 1 >= 3 THEN 'FAILED_FINAL' ELSE 'FAILED' END,attempt_count=attempt_count+1,next_attempt_at=CURRENT_TIMESTAMP+INTERVAL '30 seconds',error_message=$2,updated_at=CURRENT_TIMESTAMP WHERE job_id=$1", jobId, errorMessage)

    async def getKnowledgeBaseStatus(self, knowledgeBaseId: str, userId: str) -> dict[str, object] | None:
        """向 Java 返回当前用户知识库的异步索引状态和 chunk 数量。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT k.status,k.last_chunk_count,k.last_document_id FROM rag_knowledge_bases k WHERE k.knowledge_base_id=$1 AND k.owner_user_id=$2", knowledgeBaseId, userId)
        return dict(row) if row is not None else None

    async def saveWebCrawl(
        self,
        crawlToken: str,
        userId: str,
        entryUrl: str,
        status: str,
        stopReason: str | None,
        expiresAt: object,
        pages: list[dict[str, object]],
    ) -> None:
        """原子保存网页抓取批次与页面正文，确保预览和后续导入不依赖 API 进程内存。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO rag_web_crawl_job(crawl_token,user_id,entry_url,status,stop_reason,expires_at) VALUES($1,$2,$3,$4,$5,$6)",
                    crawlToken, userId, entryUrl, status, stopReason, expiresAt,
                )
                await connection.executemany(
                    "INSERT INTO rag_web_crawl_page(crawl_token,page_id,url,title,content_type,markdown,content_hash,depth,parent_url) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    [(
                        crawlToken, str(page["id"]), str(page["url"]), str(page["title"]),
                        page.get("contentType"), str(page["markdown"]), str(page["contentHash"]),
                        int(page.get("depth", 0)), page.get("parentUrl"),
                    ) for page in pages],
                )
                # 抓取批次仅用于预览、选择和导入，过期后可由数据库级级联关系一并释放正文。
                await connection.execute(
                    "DELETE FROM rag_web_crawl_job WHERE expires_at <= CURRENT_TIMESTAMP",
                )

    async def loadOrCreateWebImport(
        self,
        importRunId: str,
        crawlToken: str,
        userId: str,
        selectedPageIds: list[str],
    ) -> list[dict[str, object]]:
        """创建或重放网页导入批次；同一 runId 始终返回同一组页面和知识库标识。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT crawl_token,user_id,selected_page_ids FROM rag_web_crawl_import WHERE import_run_id=$1 FOR UPDATE",
                    importRunId,
                )
                normalizedIds = sorted(set(selectedPageIds))
                if existing is not None:
                    if str(existing["crawl_token"]) != crawlToken or str(existing["user_id"]) != userId or sorted(existing["selected_page_ids"]) != normalizedIds:
                        raise RagRetrievalError("runId 已绑定到其他网页导入请求")
                    rows = await connection.fetch(
                        "SELECT p.page_id,p.url,p.title,p.content_type,p.markdown,p.content_hash,p.depth,m.knowledge_base_id,m.document_id,m.index_run_id FROM rag_web_crawl_import_page m JOIN rag_web_crawl_page p ON p.crawl_token=$2 AND p.page_id=m.page_id WHERE m.import_run_id=$1 ORDER BY p.depth,p.page_id",
                        importRunId, crawlToken,
                    )
                    return [dict(row) for row in rows]
                job = await connection.fetchrow(
                    "SELECT user_id,expires_at FROM rag_web_crawl_job WHERE crawl_token=$1 FOR UPDATE",
                    crawlToken,
                )
                if job is None or str(job["user_id"]) != userId:
                    raise RagRetrievalError("网页抓取预览不存在或无权访问")
                if job["expires_at"] <= __import__("datetime").datetime.now(__import__("datetime").timezone.utc):
                    raise RagRetrievalError("网页抓取预览已过期")
                pages = await connection.fetch(
                    "SELECT page_id,url,title,content_type,markdown,content_hash,depth FROM rag_web_crawl_page WHERE crawl_token=$1 AND page_id=ANY($2::text[]) ORDER BY depth,page_id",
                    crawlToken, normalizedIds,
                )
                if len(pages) != len(normalizedIds):
                    raise RagRetrievalError("部分网页不存在或不属于当前抓取批次")
                await connection.execute(
                    "INSERT INTO rag_web_crawl_import(import_run_id,crawl_token,user_id,selected_page_ids,status) VALUES($1,$2,$3,$4::jsonb,'PROCESSING')",
                    importRunId, crawlToken, userId, json.dumps(normalizedIds),
                )
                mappings = []
                for page in pages:
                    pageId = str(page["page_id"])
                    mapping = (
                        importRunId, pageId, f"url-{uuid4().hex}",
                        f"doc-{uuid4().hex}", f"index-{uuid4().hex}",
                    )
                    mappings.append(mapping)
                await connection.executemany(
                    "INSERT INTO rag_web_crawl_import_page(import_run_id,page_id,knowledge_base_id,document_id,index_run_id) VALUES($1,$2,$3,$4,$5)",
                    mappings,
                )
                return [
                    {**dict(page), "knowledge_base_id": mapping[2], "document_id": mapping[3], "index_run_id": mapping[4]}
                    for page, mapping in zip(pages, mappings)
                ]

    async def loadWebCrawlArchive(self, crawlToken: str, userId: str) -> list[dict[str, object]]:
        """读取属于当前用户的抓取页面，供下载原始 Markdown 归档。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            job = await connection.fetchrow(
                "SELECT crawl_token FROM rag_web_crawl_job WHERE crawl_token=$1 AND user_id=$2 AND expires_at>CURRENT_TIMESTAMP",
                crawlToken, userId,
            )
            if job is None:
                raise RagRetrievalError("网页抓取预览不存在、已过期或无权访问")
            rows = await connection.fetch(
                "SELECT title,url,markdown,depth FROM rag_web_crawl_page WHERE crawl_token=$1 ORDER BY depth,page_id",
                crawlToken,
            )
        return [dict(row) for row in rows]

    async def completeWebImport(self, importRunId: str) -> None:
        """标记网页导入批次已创建全部索引任务，便于审计与排查批量任务状态。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE rag_web_crawl_import SET status='COMPLETED',completed_at=CURRENT_TIMESTAMP WHERE import_run_id=$1",
                importRunId,
            )

    async def recordRetrievalSources(self, sessionId: str, runId: str, results: list[RagSearchResult]) -> None:
        """持久化本轮检索来源，支持面试记录回溯而不向模型或前端暴露分数。"""
        if not results:
            return
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.executemany(
                "INSERT INTO agent_rag_retrieval_source(session_id,run_id,chunk_id,knowledge_base_id,document_id,heading_path,page_number) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(session_id,run_id,chunk_id) DO NOTHING",
                [(sessionId, runId, item.chunk.chunkId, item.chunk.knowledgeBaseId, item.chunk.documentId, item.chunk.headingPath, item.chunk.pageNumber) for item in results],
            )

    async def recordCachedRetrievalSources(
        self,
        sessionId: str,
        runId: str,
        entries: list[dict[str, object]],
    ) -> None:
        """将 Redis 命中的 chunk 来源绑定到当前 run，保持历史追踪完整。"""
        if not entries:
            return
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.executemany(
                "INSERT INTO agent_rag_retrieval_source(session_id,run_id,chunk_id,knowledge_base_id,document_id,heading_path,page_number) SELECT $1,$2,c.chunk_id,c.knowledge_base_id,c.document_id,c.heading_path,c.page_number FROM rag_chunks c WHERE c.chunk_id=$3 ON CONFLICT(session_id,run_id,chunk_id) DO NOTHING",
                [(sessionId, runId, str(entry["chunkId"])) for entry in entries],
            )

    async def deleteRetrievalSources(self, sessionId: str) -> None:
        """删除指定面试会话的来源追踪，配合用户删除权完成数据清理。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM agent_rag_retrieval_source WHERE session_id=$1", sessionId)

    async def resolveAccessScope(
        self,
        userId: str,
        requestedIds: list[str],
        allowedSystemIds: tuple[str, ...] | None,
    ) -> RagAccessScope:
        """将请求范围与数据库归属、系统库授权求交集，禁止跨用户读取知识库。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT knowledge_base_id,index_version FROM rag_knowledge_bases WHERE status='READY' AND ((knowledge_base_type='USER' AND owner_user_id=$1) OR (knowledge_base_type='SYSTEM' AND ($2::text[] IS NULL OR knowledge_base_id=ANY($2)))) AND ($3::text[] IS NULL OR knowledge_base_id=ANY($3)) ORDER BY knowledge_base_id",
                userId,
                list(allowedSystemIds) if allowedSystemIds is not None else None,
                requestedIds or None,
            )
        return RagAccessScope(
            tuple(str(row["knowledge_base_id"]) for row in rows),
            tuple(int(row["index_version"]) for row in rows),
        )

    async def markForDeletion(self, knowledgeBaseId: str, userId: str) -> bool:
        """仅允许所有者将用户知识库切换为删除中，阻断跨用户删除。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            updated = await connection.fetchval(
                "UPDATE rag_knowledge_bases SET status='DELETE_REQUESTED' WHERE knowledge_base_id=$1 AND knowledge_base_type='USER' AND owner_user_id=$2 AND status <> 'DELETED' RETURNING knowledge_base_id",
                knowledgeBaseId,
                userId,
            )
        return updated is not None

    async def isDeletionCompleted(self, knowledgeBaseId: str, userId: str) -> bool:
        """确认同一用户的删除任务是否已经完成，用于网络重试幂等重放。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            status = await connection.fetchval(
                "SELECT status FROM rag_knowledge_bases WHERE knowledge_base_id=$1 AND knowledge_base_type='USER' AND owner_user_id=$2",
                knowledgeBaseId,
                userId,
            )
        return status == "DELETED"

    async def replaceDocument(self, chunks: list[DocumentChunk]) -> None:
        """事务性替换文档 chunk，保证 READY 知识库不会看到半成品。"""
        if not chunks:
            return
        try:
            pool = await self.postgresService.getPool()
            async with pool.acquire() as connection:
                async with connection.transaction():
                    row = await connection.fetchrow(
                        "SELECT status,index_version FROM rag_knowledge_bases WHERE knowledge_base_id=$1 FOR UPDATE",
                        chunks[0].knowledgeBaseId,
                    )
                    if row is None or row["status"] != "BUILDING" or int(row["index_version"]) != chunks[0].indexVersion:
                        raise RagVectorStoreError("知识库已不允许继续写入索引")
                    await connection.execute("DELETE FROM rag_chunks WHERE document_id=$1", chunks[0].documentId)
                    await connection.executemany(
                        "INSERT INTO rag_chunks(chunk_id,knowledge_base_id,document_id,index_version,content_text,heading_path,page_number,token_count,lexical_terms,embedding) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                        [(c.chunkId, c.knowledgeBaseId, c.documentId, c.indexVersion, c.content, c.headingPath, c.pageNumber, c.tokenCount, list(c.lexicalTerms), None) for c in chunks],
                    )
        except Exception as error:
            raise RagVectorStoreError("写入 pgvector 文档失败") from error

    async def saveOriginalDocument(
        self,
        knowledgeBaseId: str,
        documentId: str,
        fileName: str,
        contentType: str | None,
        content: bytes,
    ) -> None:
        """在 Agent 侧保存原始文件，供下载使用；Java 只保留文件元数据。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO rag_documents(document_id,knowledge_base_id,file_name,content_type,original_content) VALUES($1,$2,$3,$4,$5) ON CONFLICT(document_id) DO UPDATE SET file_name=$3,content_type=$4,original_content=$5",
                documentId,
                knowledgeBaseId,
                fileName,
                contentType,
                content,
            )

    async def loadOriginalDocument(
        self,
        knowledgeBaseId: str,
        documentId: str,
        userId: str,
    ) -> dict[str, object] | None:
        """按知识库和文档双重条件读取原文件，防止跨用户越权访问。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT d.file_name,d.content_type,d.original_content FROM rag_documents d JOIN rag_knowledge_bases k ON k.knowledge_base_id=d.knowledge_base_id WHERE d.knowledge_base_id=$1 AND d.document_id=$2 AND ((k.knowledge_base_type='USER' AND k.owner_user_id=$3) OR k.knowledge_base_type='SYSTEM')",
                knowledgeBaseId,
                documentId,
                userId,
            )
        if row is None:
            return None
        return {
            "fileName": row["file_name"],
            "contentType": row["content_type"],
            "content": bytes(row["original_content"]),
        }

    async def saveEmbeddings(self, chunks: list[DocumentChunk], vectors: list[list[float]]) -> None:
        """将 embedding 写入对应 chunk；向量维度由数据库 schema 强制校验。"""
        if len(chunks) != len(vectors):
            raise RagVectorStoreError("embedding 返回数量与 chunk 数量不一致")
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchval(
                    "SELECT index_version FROM rag_knowledge_bases WHERE knowledge_base_id=$1 AND status='BUILDING' FOR UPDATE",
                    chunks[0].knowledgeBaseId,
                )
                if current is None or int(current) != chunks[0].indexVersion:
                    raise RagVectorStoreError("索引版本已变化，拒绝写入 embedding")
                await connection.executemany(
                    "UPDATE rag_chunks SET embedding=$1::vector WHERE chunk_id=$2 AND index_version=$3",
                    [("[" + ",".join(str(value) for value in vector) + "]", chunk.chunkId, chunk.indexVersion) for chunk, vector in zip(chunks, vectors)],
                )
                updated = await connection.fetchval(
                    "SELECT COUNT(*) FROM rag_chunks WHERE document_id=$1 AND index_version=$2 AND embedding IS NOT NULL",
                    chunks[0].documentId,
                    chunks[0].indexVersion,
                )
                if int(updated or 0) < len(chunks):
                    raise RagVectorStoreError("索引版本已变化，拒绝写入 embedding")

    async def search(self, knowledgeBaseIds: list[str], queryVector: list[float], queryTerms: list[str], limit: int) -> list[RagSearchResult]:
        """分别执行余弦向量检索和 PostgreSQL 全文检索，再用 RRF 合并排名。"""
        if not knowledgeBaseIds:
            return []
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            vectorLiteral = "[" + ",".join(str(value) for value in queryVector) + "]"
            rows = await connection.fetch("""SELECT c.chunk_id,c.knowledge_base_id,c.document_id,c.content_text,c.heading_path,c.page_number,c.token_count,c.index_version,1-(c.embedding <=> $1::vector) AS score FROM rag_chunks c JOIN rag_knowledge_bases k ON k.knowledge_base_id=c.knowledge_base_id WHERE c.knowledge_base_id=ANY($2) AND c.index_version=k.index_version AND c.embedding IS NOT NULL AND k.status='READY' ORDER BY c.embedding <=> $1::vector LIMIT $3""", vectorLiteral, knowledgeBaseIds, limit)
            textRows = await connection.fetch("""SELECT c.chunk_id,c.knowledge_base_id,c.document_id,c.content_text,c.heading_path,c.page_number,c.token_count,c.index_version,c.lexical_terms FROM rag_chunks c JOIN rag_knowledge_bases k ON k.knowledge_base_id=c.knowledge_base_id WHERE c.knowledge_base_id=ANY($1) AND c.index_version=k.index_version AND k.status='READY' AND c.lexical_terms && $2::text[]""", knowledgeBaseIds, queryTerms)
            corpusRows = await connection.fetch("""SELECT c.token_count,c.lexical_terms FROM rag_chunks c JOIN rag_knowledge_bases k ON k.knowledge_base_id=c.knowledge_base_id WHERE c.knowledge_base_id=ANY($1) AND c.index_version=k.index_version AND k.status='READY'""", knowledgeBaseIds)
        merged: dict[str, tuple[Any, int, int]] = {}
        for rank, row in enumerate(rows, 1): merged[row["chunk_id"]] = (row, rank, 0)
        for rank, row in enumerate(self.rankBm25(textRows, corpusRows, queryTerms), 1):
            old = merged.get(row["chunk_id"])
            merged[row["chunk_id"]] = (row, old[1] if old else 0, rank)
        result = []
        for row, vectorRank, textRank in merged.values():
            result.append(RagSearchResult(DocumentChunk(str(row["chunk_id"]), str(row["knowledge_base_id"]), str(row["document_id"]), row["content_text"], row["heading_path"], row["page_number"], row["token_count"], row["index_version"], tuple(row.get("lexical_terms", []))), vectorRank, textRank, (1 / (60 + vectorRank) if vectorRank else 0) + (1 / (60 + textRank) if textRank else 0)))
        return sorted(result, key=lambda item: item.rrfScore, reverse=True)[:limit]

    def rankBm25(self, rows: list[Any], corpusRows: list[Any], queryTerms: list[str]) -> list[Any]:
        """对 PostgreSQL 全文候选集计算 BM25，避免把 ts_rank_cd 冒充为 BM25。"""
        if not rows:
            return []
        terms = set(queryTerms)
        documents = [list(row["lexical_terms"]) for row in rows]
        averageLength = sum(int(row["token_count"]) for row in corpusRows) / max(len(corpusRows), 1)
        documentFrequency = {
            term: sum(1 for row in corpusRows if term in row["lexical_terms"])
            for term in terms
        }
        scored: list[tuple[float, Any]] = []
        for row, document in zip(rows, documents):
            frequencies = {term: document.count(term) for term in terms}
            score = 0.0
            for term, frequency in frequencies.items():
                if frequency == 0:
                    continue
                idf = math.log(1 + (len(corpusRows) - documentFrequency[term] + 0.5) / (documentFrequency[term] + 0.5))
                denominator = frequency + 1.5 * (0.25 + 0.75 * len(document) / max(averageLength, 1))
                score += idf * frequency * 2.5 / denominator
            scored.append((score, row))
        return [row for _, row in sorted(scored, key=lambda item: item[0], reverse=True)]

    async def deleteKnowledgeBase(self, knowledgeBaseId: str, userId: str) -> None:
        """在事务中幂等删除知识库正文、任务和向量数据。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                status = await connection.fetchrow(
                    "SELECT owner_user_id,status FROM rag_knowledge_bases WHERE knowledge_base_id=$1 AND knowledge_base_type='USER' FOR UPDATE",
                    knowledgeBaseId,
                )
                owner = status["owner_user_id"] if status is not None else None
                if owner is None or owner != userId:
                    raise RagRetrievalError("知识库不存在或当前用户无删除权限")
                if status["status"] == "DELETED":
                    return
                await connection.execute(
                    "DELETE FROM rag_chunks WHERE knowledge_base_id=$1",
                    knowledgeBaseId,
                )
                await connection.execute(
                    "DELETE FROM rag_index_job WHERE knowledge_base_id=$1",
                    knowledgeBaseId,
                )
                await connection.execute(
                    "DELETE FROM rag_documents WHERE knowledge_base_id=$1",
                    knowledgeBaseId,
                )
                await connection.execute(
                    "UPDATE rag_knowledge_bases SET status='DELETED' WHERE knowledge_base_id=$1",
                    knowledgeBaseId,
                )
