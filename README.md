# 实习 Agent 项目

本目录将从零重构 InterviewGuide。开发环境固定为 Java 21、Maven、Python 3.12（`D:\Anaconda\envs\inter-guide`），后续服务使用 PostgreSQL、Redis、RabbitMQ 与 MyBatis-Plus。

## VS Code

以本目录作为工作区根目录打开。VS Code 会推荐 Java、Spring Boot、Python、Docker 与 PostgreSQL 扩展；接受推荐后即可获得 Java/Spring Boot 语言服务、调试与 Maven 支持。

工具链下载至 `.tooling/`，不会改动系统环境变量；它被 Git 忽略。`scripts/mvnw.cmd` 会强制 Maven 使用项目内的 JDK 21。通过“运行任务 → 验证本地开发环境”可检查 Java、Maven 与 Python。

## 后续目录

- `java-backend/`：Spring Boot + MyBatis-Plus 业务后端
- `python-agent/`：Python Agent 服务
- `infrastructure/`：PostgreSQL、Redis、RabbitMQ 的容器配置
- `frontend/`：前端应用
