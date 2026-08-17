# 独立 Agent 与 RAG 架构方案

## 1. 目标与边界

Python Agent 是独立部署的服务。调用方可以是 Java，也可以是其他语言；Agent 不依赖调用方的 Controller、Service、Mapper、数据库表或业务任务枚举。

本阶段不扩展 Tools 和 Skills 的具体能力；它们保留在 Agent 内部的扩展边界中。Memory 继续使用现有的 `userId` 作为用户隔离依据，后续再升级为认证主体。

RAG 是本阶段必须完整可用的能力，包括文件解析、分块、Embedding、PostgreSQL/pgvector、BM25、向量检索、RRF、Redis 会话缓存、异步索引、状态查询和幂等删除。

## 2. 服务职责

### Agent 服务

- 接收通用请求协议，不解析 Java 业务对象；
- 按 `principalId` 隔离用户级数据，按 `conversationId` 隔离会话级数据；
- 维护系统提示词、Memory、RAG 缓存和 AgentLoop 上下文；
- 执行对话请求和非对话能力请求；
- 对异步操作持久化 `runId`、状态和错误；
- 返回稳定的通用响应协议。

### Java 服务

- 负责前端业务、业务元数据和展示状态；
- 将前端字段组织为自然语言 `prompt` 和通用 `context`；
- 对文件类 RAG 能力调用 Agent 的能力接口，但不保存正文、chunk 或向量；
- 只依赖 Agent API Contract，不依赖 Agent 内部类和实现；
- 根据 Agent 的 `PROCESSING/COMPLETED/FAILED` 更新自己的业务状态。

## 3. 通用请求协议

所有请求都使用同一个外层结构：

```json
{
  "apiVersion": "v1",
  "requestId": "req-001",
  "runId": "run-001",
  "principalId": "opaque-user-id",
  "conversationId": "opaque-conversation-id",
  "mode": "conversation",
  "capability": null,
  "prompt": "用户自然语言请求",
  "context": {},
  "stateVersion": 0
}
```

字段约定：

- `principalId` 是跨会话稳定的不透明用户标识；
- `conversationId` 是会话标识，Agent 不关心其生成规则；
- `runId` 标识一次执行，用于幂等和结果重放；
- `prompt` 是对话任务的自然语言输入；
- `context` 只携带本次任务的必要业务资料；
- `capability` 仅用于非对话能力，例如 `knowledge_base.index`；
- `mode=conversation` 时执行 AgentLoop；
- `mode=capability` 时执行确定性的 Agent 能力，不经过 LLM 自主决策。

RAG 文件正文属于 `context` 的传输数据，但解析、分块、Embedding 和存储全部在 Agent 内部完成。

## 4. 通用响应协议

```json
{
  "apiVersion": "v1",
  "requestId": "req-001",
  "runId": "run-001",
  "principalId": "opaque-user-id",
  "conversationId": "opaque-conversation-id",
  "status": "PROCESSING",
  "statusCode": 100,
  "data": {},
  "error": null
}
```

`status` 取值为 `PROCESSING`、`COMPLETED` 或 `FAILED`。失败响应必须包含稳定错误码、可展示消息和 `retryable` 标识。Java 不需要知道 Agent 内部步骤，只根据协议对账。

## 5. Agent 内部结构

```text
api/
  通用 HTTP 协议和请求路由
Agents/
  AgentLoop、上下文模型和能力端口
Memory/
  短期记忆、长期记忆、摘要和持久化
RAG/
  文档解析、分块、Embedding、检索、缓存和索引 worker
LLM/
  OpenAI SDK 适配器
Prompts/
  所有生产提示词
```

`Agents` 只依赖端口，不放 RAG 和 Memory 的具体实现。

## 6. RAG 生命周期与并发规则

知识库状态：

```text
BUILDING → READY
BUILDING → FAILED
READY → DELETE_REQUESTED → DELETED
FAILED → BUILDING（仅安全重试）
```

每个索引任务必须绑定 `knowledgeBaseId + documentId + runId + indexVersion`。worker 在读取、写入、完成和失败时都必须校验版本；旧任务不能覆盖新任务。

索引流程：

1. Agent 保存原始文件和 PENDING job；
2. worker 原子 claim job；
3. 解析 Markdown/PDF/TXT；
4. 按标题和 token 分块，overlap 为 10%~15%；
5. 批量调用 Embedding；
6. 在事务内替换当前版本 chunk 并写入向量；
7. 只有版本一致时才将知识库和 job 标记为 READY/COMPLETED。

删除流程必须阻止新检索进入，并等待已有检索引用租约结束。删除 chunks、原文件、jobs 和状态更新必须在同一个数据库事务中完成。删除请求必须幂等。

检索顺序：

1. 计算授权知识库集合和当前 indexVersion；
2. 查询 Redis 会话缓存；
3. 缓存未命中或相似度不足时执行向量检索和 BM25；
4. 使用 RRF 合并，取前 5~8 个 chunk；
5. 缓存结果并记录当前 run 的来源追踪。

缓存键必须包含会话、知识库范围、索引版本、Embedding 模型和检索策略版本。

## 7. Java 适配方式

Java 只实现一个通用 Agent Client。对话接口提交 `prompt/context`；RAG 文件管理使用 Agent 的能力名称，但不依赖 Python 内部的任务枚举。

Java 不能直接读取 Agent 数据库、Redis、chunk 或向量。Java 只保存知识库标签、文件元数据和面向前端的状态。

## 8. 明确暂不实现

- Tools 的具体工具注册和实现；
- Skills 的动态配置和权限加载；
- URL 抓取和网页知识库；
- 更换认证主体模型（当前仍使用 userId）。

这些内容可以保留清晰的扩展端口，但不伪装成已完成能力。
