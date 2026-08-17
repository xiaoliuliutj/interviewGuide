# InterviewGuide

InterviewGuide 是一个面向求职场景的智能面试辅助项目，提供简历评估、模拟面试和知识库服务。项目采用“前端 + Java 业务控制层 + Python Agent 执行层”的架构，将用户交互、业务状态管理和智能执行组织为清晰的协作链路。

## 系统架构

```text
React 前端
    │ HTTP
    ▼
Java Spring Boot 业务控制层
    │ Agent Client
    ▼
Python Agent 执行层
    │
    ├── LLM 调用
    ├── Agent Loop 与 Workflow
    ├── Skills 与 Tools
    ├── Memory
    └── RAG 知识库
```

### 前端层

前端使用 React 和 TypeScript 实现页面交互，负责简历上传、面试对话、知识库管理、历史记录展示和报告下载。前端通过 Java 接口获取统一的业务结果和展示数据。

### Java 业务控制层

Java 层使用 Spring Boot 和 Controller-Service-Mapper 架构，负责：

- 校验用户与简历、面试、知识库之间的归属关系；
- 维护前端需要展示的业务状态和结果投影；
- 组装包含 `mode`、`capability`、`prompt`、`data`、会话标识和版本号的 Agent 请求，并解析 Agent 响应；
- 管理简历、面试和知识库的业务生命周期；
- 处理 Agent 调用的幂等、有限重试、删除补偿、后台状态同步、降级和熔断；
- 通过 PDFBox 生成简历分析报告和面试报告。

Java 层保存业务元数据、状态、评分结果、面试回合和前端展示所需的信息。

### Python Agent 执行层

Python Agent 以独立服务形式运行，负责：

- 调用 OpenAI SDK 与大语言模型交互；
- 根据任务类型加载 Skill 和 Prompt；
- 运行 ReAct Agent Loop，协调模型、记忆、RAG 和工具；
- 执行简历解析与评估工作流；
- 执行面试开场、规划、出题、答题评价、总结和最终评价工作流；
- 管理短期记忆、长期记忆和会话状态；
- 完成知识库文档解析、切分、向量化、混合检索和网页内容导入；
- 返回包含状态码、任务编码、会话标识和业务结果的结构化响应。

Agent 层保存模型执行状态、会话上下文、记忆正文、原始文档和向量数据。

## 主要功能

### 简历评估

用户上传简历后，Java 层建立业务记录并提交 Agent 任务。Agent 解析 PDF、Word 或其他支持的文件，提取简历内容并通过 LLM 生成结构化评估结果。Java 层保存评分、优势、建议、问题和处理状态，前端可以查询、重新分析、下载原文件和导出 PDF 报告。

### 模拟面试

Java 层创建面试业务记录并提交会话请求。Agent 根据岗位、难度、简历、知识库和历史上下文运行面试 Workflow，依次完成开场、问题规划、出题、回答评价、追问、阶段总结和最终评价。Java 层保存当前问题、阶段、回答、评分和最终结果，前端通过接口推进面试和查看历史。

### 知识库

知识库统一承载系统文档、用户上传文档和网页抓取内容。文件或网页内容进入 Agent 后，经过文本解析、标题识别、Token 分块、Embedding 生成和 PostgreSQL/pgvector 存储。检索阶段结合向量检索与 BM25，通过 RRF 融合并进行结果重排，将高相关内容交给 Agent 使用。

知识库支持文件上传、网页抓取、同域页面爬取、文档导入、状态查询、重新向量化、分类、下载和删除。Java 层保存知识库标签、归属和状态，Agent 层保存原始正文、分块和向量。

## Agent 执行机制

对话请求优先读取已有会话状态；首次对话请求由顶层路由 Prompt 和模型判断进入面试工作流、简历分析工作流或通用 Agent Loop。显式 capability 请求由 Agent API 按 capability 路由至对应执行流程。Skill 通过 Prompt 规定角色、任务目标、允许的工具、记忆范围、知识库范围和输出格式。

在 Agent Loop 中，大模型根据当前上下文产生下一步动作。工具注册表将工具名称映射到实际处理函数，执行结果加入后续模型上下文，循环直到获得符合协议的最终结果或达到超时、重试和最大轮数限制。

当前工具包括记忆读取、知识检索、知识库状态查询、文档解析、网页读取和网站爬取。工具的领域实现分别位于 Memory、RAG 和 Tools 目录，Agent 通过统一注册表进行调度。

## 数据与可靠性实现

- PostgreSQL：保存 Java 业务数据，以及 Agent 的记忆、知识库文档、分块和检索数据。
- pgvector：保存文档 Embedding 并执行向量相似度检索。
- Redis：缓存面试短期上下文、短期 RAG 结果、幂等结果和必要的并发控制信息。
- RabbitMQ：为后续异步任务和事件处理提供消息基础设施。
- Outbox：Java 对简历、面试和知识库删除请求建立持久化任务，后台按幂等键调用 Agent 并执行有限重试。
- 后台状态同步：Java 定时查询处理中简历和知识库的 Agent 执行状态，将已完成或失败的结果同步到业务记录。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、Nginx |
| Java | Java 21、Spring Boot、MyBatis-Plus、Flyway、PDFBox |
| Agent | Python 3.12、FastAPI、OpenAI SDK、Pydantic |
| 数据服务 | PostgreSQL、pgvector、Redis、RabbitMQ |
| 文档与检索 | tiktoken、PDF/Word/Markdown 解析、向量检索、BM25、RRF |
| 部署 | Docker、Docker Compose |

## Docker 部署

创建配置文件：

```sh
cp agent/Common/Configs/.env.example agent/.env
vi agent/.env
```

填写模型、Embedding 和数据库连接参数。

启动全部服务：

```sh
sh scripts/deploy-docker.sh
```

查看状态：

```sh
docker compose ps
```

停止服务：

```sh
sh scripts/deploy-docker.sh down
```

前端默认地址为 `http://localhost`，RabbitMQ 管理台默认地址为 `http://localhost:15672`。
