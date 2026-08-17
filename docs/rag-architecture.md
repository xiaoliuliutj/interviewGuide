# RAG 模块方案

## 1. 职责边界

Java 只保存知识库标签、用户归属、文件元数据和生命周期状态，并负责权限校验、删除状态机及重试。Agent 负责原文件接收、文本解析、标题识别、token 切分、Embedding、正文与向量持久化、检索和面试会话缓存。

## 2. 入库链路

文件上传后，Java 生成 `knowledgeBaseId` 和 `documentId`，状态置为 `BUILDING`，通过统一 Agent 请求发送 Base64 文件。Agent 先保存原文件，再根据 Markdown 标题或 PDF 页/章节提取纯文本，使用 800 token chunk、96 token overlap 切分，按 10 条一批生成 embedding，事务写入 PostgreSQL/pgvector，成功后状态切换为 `READY`。

## 3. 检索链路

面试默认使用用户全部知识库和 Skill 允许的系统知识库。Agent 先生成 query embedding，并检查当前 session 的 Redis 缓存；缓存向量与新 query 的余弦相似度低于 0.35 时重新检索。正式检索使用 pgvector 余弦距离和 PostgreSQL 候选全文检索，候选集再计算 BM25，最后用 `1/(60+rank)` 的 RRF 融合，返回最多 8 个正文 chunk。标题、页码和分数只保留在 Agent 内部追踪，不返回模型或前端。

## 4. 删除与一致性

Java 删除时先将元数据置为 `DELETE_REQUESTED`，前端立即不可用。Agent 将知识库置为删除中，新的检索因状态条件不会命中；已有检索通过 Redis 引用计数释放后，Agent 删除原文件、chunk、向量和缓存。失败时 Java 置为 `DELETE_FAILED`，每 30 分钟重试，最多自动重试 2 次，之后保留手动重试能力。

## 5. 表结构

- Java `knowledge_base`：用户归属、名称、分类、文件元数据、状态、重试信息。
- Agent `rag_knowledge_bases`：Agent 侧索引状态和版本。
- Agent `rag_documents`：原文件，仅由 Agent 保存，用于下载和重新向量化。
- Agent `rag_chunks`：解析文本、标题路径、页码、token 数、tsvector 和 pgvector。

Redis 只保存面试 session 的临时检索结果及知识库正在检索的引用计数，TTL 为 30 分钟，面试结束或知识库删除时清理。
