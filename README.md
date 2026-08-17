# InterviewGuide

InterviewGuide 是一个面向求职场景的智能面试辅助项目。项目围绕“简历评估、模拟面试、个人知识库和 Agent 执行”构建，前端负责交互展示，Java 服务负责业务流程控制，Python Agent 服务负责模型调用、记忆、检索与工作流执行。

## 主要功能

- 简历管理：上传简历、异步解析与评估、重新分析、查看结果、下载原文件和导出 PDF 分析报告。
- 模拟面试：根据目标岗位、难度、简历和历史上下文生成问题；支持答题、暂停、完成、关闭、查询历史和导出 PDF 面试报告。
- 个人知识库：上传 Markdown、PDF、Word 等文档，完成文本解析、分块、向量化和检索；支持知识库删除、重试和状态查询。
- 网页知识入库：抓取公开网页或在限定深度内爬取同域页面，再将选定内容导入知识库。
- Agent 能力：提供 ReAct 循环、工具调用、短期记忆、长期记忆、RAG 混合检索和结构化响应校验。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、Nginx |
| Java 业务层 | Java 21、Spring Boot、MyBatis-Plus、Flyway、PDFBox |
| Agent 层 | Python 3.12、FastAPI、OpenAI SDK、Pydantic |
| 数据与消息 | PostgreSQL、pgvector、Redis、RabbitMQ |
| 检索与文档 | tiktoken、BM25、向量检索、RRF、PDF/Word/Markdown 解析 |
| 部署 | Docker、Docker Compose |

## 主要实现方式

### 分层职责

- 前端：调用 HTTP 接口并展示简历、面试和知识库数据。
- Java：校验用户归属、维护业务状态和展示投影，处理有限重试、幂等、删除补偿、状态对账和 Agent 服务降级；不处理模型推理、记忆正文或向量检索。
- Python Agent：执行简历解析、面试工作流、记忆管理、RAG、网页读取和工具调度；以统一结构化响应向调用方返回状态、任务信息和结果。

### Agent 与工作流

Agent 使用受限的 ReAct 循环：模型根据当前任务和 Skill 决定是否调用记忆、RAG 或网页工具；工具结果会作为后续上下文重新交给模型。循环具有最大轮数、超时和重试限制，避免无限调用。

面试采用 Workflow 管理会话阶段，包括开场、问题规划、出题、回答评价、阶段总结和最终评价。Java 仅保存面试进度、题目、回答和最终评价投影，Agent 保存执行状态和会话上下文。

### 记忆与 RAG

- 短期记忆：Redis 保存最近对话和历史摘要，面试结束或超时后清理缓存。
- 长期记忆：PostgreSQL 保存用户画像、简历评估摘要和历史面试摘要。
- RAG：文档先解析为文本，按标题和 Token 分块；检索使用向量检索、BM25 和 RRF 融合，随后进行重排并将结果用于模型上下文。

### 可靠性

简历、面试和知识库删除采用持久化 Outbox 任务。Java 会先将资源标记为不可用，再由后台任务幂等调用 Agent；失败任务按固定间隔有限重试，避免网络中断造成 Java 与 Agent 两侧数据不一致。处理中简历由后台状态对账任务同步 Agent 执行结果。

## 本地与 Docker 部署

真实 API Key、模型地址和数据库密码保存于 `agent/.env`，该文件不会提交到 Git。可先复制模板：

```sh
cp agent/Common/Configs/.env.example agent/.env
```

填写配置后使用 Shell 脚本部署：

```sh
sh scripts/deploy-docker.sh
```

停止服务：

```sh
sh scripts/deploy-docker.sh down
```

部署完成后，前端默认访问 `http://localhost`，RabbitMQ 管理台默认访问 `http://localhost:15672`。
