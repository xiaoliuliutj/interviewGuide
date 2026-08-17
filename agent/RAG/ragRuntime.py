import asyncio
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from agent.Common.AgentModels import AgentContext
from agent.Common.Configs.AgentSettings import AgentSettings
from agent.Common.Exceptions.AgentException import AgentException, RagDeletionError, RagDocumentTooLargeError, RagIndexingError, RagRetrievalError
from agent.Common.Postgres.PostgresService import PostgresService
from agent.Common.Redis.RedisService import RedisService
from agent.LLM.llmService import LlmService
from agent.RAG.ragChunker import TokenChunker
from agent.RAG.ragDocumentParser import DocumentParser
from agent.RAG.ragPolicy import RagPolicy
from agent.RAG.ragCache import RagSessionCache
from agent.RAG.ragRepository import RagRepository
from agent.Tools.toolsWebReader.toolsWebReader import WebReader


class RagRuntime:
    """编排文档解析、向量化、混合检索、会话缓存和知识库删除。"""
    def __init__(self, llmService: LlmService | None = None) -> None:
        settings = AgentSettings.from_environment()
        self.policy = RagPolicy()
        self.llmService = llmService or LlmService(settings)
        self.repository = RagRepository(PostgresService(settings))
        self.cache = RagSessionCache(RedisService(settings), self.policy.cacheTtlSeconds)
        self.parser = DocumentParser(self.policy)
        self.chunker = TokenChunker(self.policy)
        self.webReader = WebReader()

    async def retrieveKnowledge(self, context: AgentContext) -> list[str]:
        """优先使用 Redis 缓存，未命中时执行余弦向量+全文检索+RRF。"""
        query = str(context.request.payload.get("query") or context.request.payload.get("answer") or "")
        if not query:
            return []
        ids = context.request.payload.get("knowledgeBaseIds", [])
        ids = ids if isinstance(ids, list) else []
        scope = await self.repository.resolveAccessScope(
            context.request.context.principal_id,
            [str(item) for item in ids],
            context.skill.allowedSystemKnowledgeBaseIds,
        )
        knowledgeBaseIds = list(scope.knowledgeBaseIds)
        if not knowledgeBaseIds:
            return []
        vector = await self.llmService.embedQuery(query)
        embeddingModel = getattr(self.llmService.settings, "embedding_model", "unknown")
        scopeKey = hashlib.sha256(
            f"{context.skill.taskType}|{scope.knowledgeBaseIds}|{scope.indexVersions}|{embeddingModel}|rag-v1".encode("utf-8")
        ).hexdigest()[:16]
        leaseId = uuid4().hex
        if not await self.repository.acquireRetrievalLease(leaseId, knowledgeBaseIds):
            raise RagRetrievalError("知识库正在删除或不可用")
        client = None
        acquiredKeys = []
        try:
            client = await self.cache.redisService.client()
            cachedEntries = await self.cache.loadEntries(
                context.request.context.conversation_id,
                scopeKey,
                vector,
                self.policy.minCosineSimilarity,
            )
            if cachedEntries is not None:
                await self.repository.recordCachedRetrievalSources(
                    context.request.context.conversation_id,
                    context.request.context.run_id,
                    cachedEntries,
                )
                return [str(item["content"]) for item in cachedEntries]
            for knowledgeBaseId in knowledgeBaseIds:
                key = f"agent:rag:kb:{knowledgeBaseId}:activeRetrievals"
                await client.incr(key)
                await client.expire(key, 300)
                acquiredKeys.append(key)
            queryTerms = [str(token) for token in self.chunker.encode(query)]
            results = await self.repository.search(knowledgeBaseIds, vector, queryTerms, self.policy.topK)
            await self.repository.recordRetrievalSources(
                context.request.context.conversation_id,
                context.request.context.run_id,
                results,
            )
            await self.cache.save(context.request.context.conversation_id, scopeKey, vector, results)
            for knowledgeBaseId in knowledgeBaseIds:
                await client.sadd(f"agent:rag:kb:{knowledgeBaseId}:sessions", f"{context.request.context.conversation_id}:{scopeKey}")
                await client.expire(
                    f"agent:rag:kb:{knowledgeBaseId}:sessions",
                    self.policy.cacheTtlSeconds,
                )
            return [item.chunk.content for item in results]
        finally:
            if client is not None:
                for key in acquiredKeys:
                    await client.decr(key)
            await self.repository.releaseRetrievalLease(leaseId)

    async def stageIndexDocument(self, payload: dict[str, object]) -> dict[str, object]:
        """仅持久化原文件和索引任务，快速返回 PROCESSING，避免 Java HTTP 长时间等待。"""
        existing = await self.repository.findIndexJob(str(payload["runId"]))
        if existing is not None:
            if (
                str(existing["user_id"]) != str(payload["userId"])
                or str(existing["knowledge_base_id"]) != str(payload["knowledgeBaseId"])
                or str(existing["document_id"]) != str(payload["documentId"])
            ):
                raise RagRetrievalError("runId 已绑定其他索引任务")
            return {"knowledgeBaseId": existing["knowledge_base_id"], "documentId": existing["document_id"], "status": existing["status"]}
        raw = payload.get("documentContent") or payload.get("fileContent")
        content = base64.b64decode(raw) if isinstance(raw, str) and payload.get("contentEncoding") == "base64" else str(raw or "").encode()
        if len(content) > self.policy.maxDocumentBytes:
            raise RagDocumentTooLargeError("文档超过允许的大小限制")
        indexVersion = await self.repository.ensureKnowledgeBase(str(payload["knowledgeBaseId"]), str(payload["userId"]))
        await self.repository.saveOriginalDocument(
            str(payload["knowledgeBaseId"]), str(payload["documentId"]), str(payload.get("fileName", "document")),
            str(payload.get("contentType")) if payload.get("contentType") else None, content,
        )
        job = await self.repository.createIndexJob(
            str(payload["runId"]),
            str(payload["knowledgeBaseId"]),
            str(payload["documentId"]),
            str(payload["userId"]),
            indexVersion,
        )
        return {"knowledgeBaseId": payload["knowledgeBaseId"], "documentId": payload["documentId"], "indexVersion": indexVersion, "status": job["status"]}

    async def crawlUrlKnowledgeBase(self, payload: dict[str, object]) -> dict[str, object]:
        """抓取入口 URL 的同域页面并持久化预览，使后续导入可跨请求、跨进程继续使用抓取结果。"""
        crawl = await self.webReader.crawlSite(str(payload["url"]))
        token = uuid4().hex
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.policy.webCrawlPreviewTtlSeconds)
        status = "COMPLETED" if bool(crawl.get("completed")) else "PARTIAL_COMPLETED"
        for page in crawl["documents"]:
            page["id"] = uuid4().hex
        await self.repository.saveWebCrawl(
            token, str(payload["userId"]), str(crawl["entryUrl"]), status,
            None if bool(crawl.get("completed")) else "达到页面或深度限制", expires, crawl["documents"],
        )
        return {
            "previewToken": token,
            "expiresAt": expires.isoformat(),
            "entryUrl": crawl["entryUrl"],
            "status": status,
            "stopReason": None if bool(crawl.get("completed")) else "达到页面或深度限制",
            "validPageCount": len(crawl["documents"]),
            "rejectedCount": len(crawl["rejected"]),
            "pages": [self.webPageView(page) for page in crawl["documents"]],
            "rejected": crawl["rejected"],
        }

    async def importUrlKnowledgeBase(self, payload: dict[str, object]) -> dict[str, object]:
        """按用户选择的页面创建独立知识库，并复用现有异步切分、向量化和状态流转。"""
        token = str(payload["previewToken"])
        selected = payload.get("selectedPageIds")
        selectedIds = [str(item) for item in selected] if isinstance(selected, list) else []
        if not selectedIds:
            raise RagIndexingError("至少选择一个网页")
        pages = await self.repository.loadOrCreateWebImport(
            str(payload["runId"]), token, str(payload["userId"]), selectedIds,
        )
        result = []
        for page in pages:
            pageId = str(page["page_id"])
            knowledgeBaseId = str(page["knowledge_base_id"])
            documentId = str(page["document_id"])
            indexRunId = str(page["index_run_id"])
            staged = await self.stageIndexDocument({
                "runId": indexRunId, "userId": payload["userId"], "knowledgeBaseId": knowledgeBaseId,
                "documentId": documentId, "fileName": self.safeWebFileName(str(page["title"]), pageId),
                "contentType": page["content_type"] or "text/markdown", "documentContent": str(page["markdown"]),
            })
            result.append({
                "pageId": pageId, "knowledgeBaseId": knowledgeBaseId, "documentId": documentId,
                "indexRunId": indexRunId, "status": staged["status"], "url": page["url"],
                "title": page["title"],
                "fileName": self.safeWebFileName(str(page["title"]), pageId),
                "contentHash": page["content_hash"],
                "characterCount": len(str(page["markdown"])),
                "depth": page["depth"],
            })
        await self.repository.completeWebImport(str(payload["runId"]))
        return {"importRunId": payload["runId"], "importedCount": len(result), "knowledgeBases": result}

    async def downloadUrlCrawlArchive(self, payload: dict[str, object]) -> dict[str, object]:
        """读取未过期的抓取批次并生成 Markdown 归档，供 Java 下载展示。"""
        pages = await self.repository.loadWebCrawlArchive(
            str(payload["previewToken"]), str(payload["userId"]),
        )
        archive = "\n\n".join(
            f"# {row['title']}\n\n来源：{row['url']}\n\n{row['markdown']}"
            for row in pages
        )
        return {"fileName": "web-crawl-sources.md", "contentType": "text/markdown", "content": base64.b64encode(archive.encode()).decode("ascii"), "contentEncoding": "base64"}

    def webPageView(self, page: dict[str, object]) -> dict[str, object]:
        """将内部网页记录转换为 Java/前端可展示且不泄漏内部字段的页面摘要。"""
        return {"id": page["id"], "url": page["url"], "title": page["title"], "fetchedAt": datetime.now(timezone.utc).isoformat(), "contentHash": page["contentHash"], "markdown": page["markdown"], "contentType": page.get("contentType"), "characterCount": len(str(page["markdown"])), "depth": page.get("depth", 0), "parentUrl": page.get("parentUrl"), "filename": self.safeWebFileName(str(page["title"]), str(page["id"]))}

    def safeWebFileName(self, title: str, pageId: str) -> str:
        """生成稳定且不含路径分隔符的网页文档名，避免不同页面上传时互相覆盖。"""
        safe = "".join(char if char.isalnum() or char in "-_ " else "_" for char in title).strip()[:80] or "web-page"
        return f"{safe}-{pageId[:8]}.md"

    async def processIndexJobs(self) -> None:
        """由常驻 worker 领取持久化任务并完成解析、embedding 与向量写入。"""
        for job in await self.repository.claimIndexJobs():
            try:
                document = await self.repository.loadIndexDocument(str(job["document_id"]))
                sections = self.parser.parse(document["content"], str(document["fileName"]), document["contentType"])
                version = int(job["index_version"])
                if not await self.repository.resumeIndexing(str(job["knowledge_base_id"]), version):
                    if not await self.repository.isIndexingAllowed(str(job["knowledge_base_id"]), version):
                        await self.repository.finishIndexJob(str(job["job_id"]), False, "索引版本已失效或知识库正在删除")
                        continue
                chunks = self.chunker.split(sections, str(job["knowledge_base_id"]), str(job["document_id"]), version)
                if not chunks:
                    raise RagIndexingError("文档未提取到可索引的有效文本")
                vectors = []
                for start in range(0, len(chunks), self.policy.embeddingBatchSize):
                    vectors.extend(await self.llmService.embedDocuments([item.content for item in chunks[start:start + self.policy.embeddingBatchSize]]))
                if not await self.repository.isIndexingAllowed(str(job["knowledge_base_id"]), version):
                    await self.repository.finishIndexJob(str(job["job_id"]), False, "知识库已进入删除流程")
                    continue
                await self.repository.replaceDocument(chunks)
                await self.repository.saveEmbeddings(chunks, vectors)
                await self.repository.completeIndexRun(str(job["knowledge_base_id"]), str(job["document_id"]), str(job["run_id"]), version, len(chunks))
                await self.repository.finishIndexJob(str(job["job_id"]), True)
            except Exception as error:
                await self.repository.setKnowledgeBaseStatusIfVersion(
                    str(job["knowledge_base_id"]),
                    int(job["index_version"]),
                    "FAILED",
                )
                await self.repository.finishIndexJob(str(job["job_id"]), False, str(error))

    async def getIndexStatus(self, payload: dict[str, object]) -> dict[str, object]:
        """返回 Agent 侧权威索引状态，供 Java 对账并更新前端元数据。"""
        status = await self.repository.getKnowledgeBaseStatus(str(payload["knowledgeBaseId"]), str(payload["userId"]))
        if status is None:
            raise RagIndexingError("知识库不存在或当前用户无访问权限")
        return {"status": status["status"], "chunkCount": status.get("last_chunk_count") or 0, "documentId": status.get("last_document_id")}

    async def deleteKnowledgeBase(self, knowledgeBaseId: str, userId: str) -> None:
        """幂等删除知识库全部正文、chunk、向量和索引元数据。"""
        try:
            if await self.repository.isDeletionCompleted(knowledgeBaseId, userId):
                return
            if not await self.repository.markForDeletion(knowledgeBaseId, userId):
                raise RagDeletionError("知识库不存在或当前用户无删除权限")
            client = await self.cache.redisService.client()
            activeCount = 0
            for _ in range(60):
                activeCount = await self.repository.countActiveRetrievalLeases(knowledgeBaseId)
                if activeCount <= 0:
                    break
                await asyncio.sleep(1)
            if activeCount > 0:
                raise RagDeletionError("知识库仍有进行中的检索，删除将在稍后重试")
            sessions = await client.smembers(f"agent:rag:kb:{knowledgeBaseId}:sessions")
            if sessions:
                await client.delete(*[f"agent:rag:session:{session}:results" for session in sessions])
            await client.delete(f"agent:rag:kb:{knowledgeBaseId}:sessions")
            await self.repository.deleteKnowledgeBase(knowledgeBaseId, userId)
        except Exception as error:
            raise RagDeletionError("知识库删除失败") from error

    async def downloadDocument(self, payload: dict[str, object]) -> dict[str, object]:
        """读取 Agent 侧原始文件并编码为 API 可传输的 Base64 数据。"""
        document = await self.repository.loadOriginalDocument(
            str(payload["knowledgeBaseId"]),
            str(payload["documentId"]),
            str(payload["userId"]),
        )
        if document is None:
            raise RagDeletionError("指定文档不存在或已删除")
        return {
            "fileName": document["fileName"],
            "contentType": document["contentType"],
            "content": base64.b64encode(document["content"]).decode("ascii"),
            "contentEncoding": "base64",
        }

    async def clearSessionCache(self, sessionId: str) -> None:
        """清理面试会话的临时 RAG 缓存。"""
        await self.cache.clear(sessionId)

    async def deleteSessionSources(self, sessionId: str) -> None:
        """删除面试会话的持久化 RAG 来源记录。"""
        await self.repository.deleteRetrievalSources(sessionId)

    async def close(self) -> None:
        """关闭 RAG 自己创建的数据库、Redis 和 embedding 客户端连接。"""
        await self.repository.postgresService.close()
        await self.cache.redisService.close()
        await self.llmService.close()
