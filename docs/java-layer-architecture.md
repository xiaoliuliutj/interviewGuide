# Java 层构建方案

## 职责边界

- Controller 只接收 HTTP 请求、取得 `X-User-Id` 并调用 Service。
- Service 校验资源是否属于当前用户，维护 Java 展示数据与任务状态，处理幂等、有限重试、降级、熔断和本地事务。
- Mapper 只读写 Java PostgreSQL 的元数据与展示投影。
- AgentClient 只发送 HTTP 请求、处理传输错误和反序列化，不携带业务 Prompt 或业务判断。
- Python Agent 保存原始文件、向量、记忆、会话运行状态和执行任务；Java 不访问这些内部数据。

## 跨层协议

每次 Agent 调用使用统一请求信封：

- `userId`：调用主体，用于 Agent 内部数据隔离。
- `sessionId`：仅会话型任务使用；非会话任务使用一次临时关联标识。
- `runId`：一次业务执行的幂等标识；重试必须复用。
- `requestId`：一次 HTTP 调用的关联标识。
- `mode`、`capability`、`prompt` 和 `data`：描述任务和业务输入。

Agent 响应始终返回状态码、中文说明、是否可重试和 `data`。Java 保留 Agent 错误码并直接映射到 `ApiResult`，不重新猜测 Python 内部错误原因。

## Prompt 与可靠性

Java Prompt 位于 `backend/Agent/src/main/resources/Prompts`。业务 Service 使用 `AgentPromptService` 填充变量，再通过 `AgentRequestFactory` 构造请求；HTTP Client 不读取 Prompt。

`AgentCallService` 只提供两次有限重试和短暂熔断：网络错误和 Agent 标记为可重试的失败可以重试；参数、权限和不可恢复业务失败立即返回。知识库删除仍使用本地 Outbox 保证异步重试与最终一致性；查询在 Agent 不可用时返回 Java 已保存的投影。

## 业务链路

- 简历：Java 保存元数据和展示状态，Agent 保存原文并异步分析；Java 通过任务状态同步评估投影。
- 知识库：Java 保存标签和可见状态，Agent 处理文件、切分和向量；删除由 Java Outbox 驱动 Agent 幂等删除。
- 面试：Java 保存前端展示投影，Agent 保存会话状态、记忆和面试流程；会话使用 `userId + sessionId` 隔离。
