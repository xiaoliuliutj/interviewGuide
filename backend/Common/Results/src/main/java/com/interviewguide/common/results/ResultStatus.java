package com.interviewguide.common.results;

/** 统一维护 Java 与 Agent 之间的状态码及中文说明。 */
public enum ResultStatus {
    SUCCESS_WITH_DATA(100, "成功且返回结果"),
    SUCCESS_WITHOUT_DATA(101, "成功但无返回结果"),
    INVALID_PARAMETER(200, "请求参数不符合规范"),
    MISSING_PARAMETER(201, "缺少必要参数"),
    INVALID_REQUEST_BODY(202, "请求体格式不符合规范"),
    INVALID_FILE(203, "文件不符合要求"),
    JAVA_INTERNAL_ERROR(300, "Java 服务内部错误"),
    JAVA_BUSINESS_ERROR(301, "Java 业务处理失败"),
    JAVA_DATA_ACCESS_ERROR(302, "Java 数据访问失败"),
    JAVA_RESOURCE_NOT_FOUND(303, "Java 资源不存在"),

    AGENT_SERVICE_UNAVAILABLE(400, "Agent 服务暂时不可用"),
    AGENT_SERVICE_TIMEOUT(401, "Agent 服务请求超时"),
    AGENT_EXECUTION_FAILED(402, "Agent 执行失败"),
    AGENT_TASK_UNSUPPORTED(403, "不支持当前 Agent 任务"),
    AGENT_REQUEST_CONTRACT_INVALID(404, "Agent 请求格式不符合协议"),
    LLM_PROVIDER_UNAVAILABLE(410, "大模型服务暂时不可用"),
    LLM_AUTHENTICATION_FAILED(411, "大模型服务认证失败"),
    LLM_RATE_LIMITED(412, "大模型请求过于频繁"),
    LLM_REQUEST_TIMEOUT(413, "大模型请求超时"),
    LLM_EMPTY_RESPONSE(414, "大模型未返回有效内容"),
    LLM_TOOL_CALL_MALFORMED(415, "大模型工具调用格式错误"),
    LLM_OUTPUT_SCHEMA_INVALID(416, "大模型输出格式不符合要求"),
    LLM_CONTENT_REJECTED(417, "大模型拒绝处理当前内容"),
    LLM_CONTEXT_LIMIT_EXCEEDED(418, "大模型上下文超过限制"),
    LLM_PROVIDER_INTERNAL_ERROR(419, "大模型服务内部错误"),
    TOOL_NOT_REGISTERED(420, "请求的工具未注册"),
    TOOL_NOT_AUTHORIZED(421, "当前任务无权使用该工具"),
    TOOL_ARGUMENT_INVALID(422, "工具调用参数不合法"),
    TOOL_EXECUTION_TIMEOUT(423, "工具执行超时"),
    TOOL_EXECUTION_FAILED(424, "工具执行失败"),
    TOOL_RESULT_INVALID(425, "工具返回结果不合法"),
    TOOL_DEPENDENCY_UNAVAILABLE(426, "工具依赖服务不可用"),
    MEMORY_SERVICE_UNAVAILABLE(430, "记忆服务暂时不可用"),
    MEMORY_READ_FAILED(431, "读取记忆失败"),
    MEMORY_WRITE_FAILED(432, "写入记忆失败"),
    MEMORY_SERIALIZATION_FAILED(433, "记忆序列化失败"),
    MEMORY_VERSION_CONFLICT(434, "记忆版本冲突"),
    MEMORY_LOCK_UNAVAILABLE(435, "记忆锁暂时不可用"),
    MEMORY_RECORD_NOT_FOUND(436, "记忆记录不存在"),
    RAG_SERVICE_UNAVAILABLE(440, "知识库服务暂时不可用"),
    RAG_RETRIEVAL_FAILED(441, "知识库检索失败"),
    RAG_EMBEDDING_FAILED(442, "向量生成失败"),
    RAG_VECTOR_STORE_FAILED(443, "向量库操作失败"),
    RAG_INDEXING_FAILED(444, "知识库索引失败"),
    RAG_DELETION_FAILED(445, "知识库删除失败"),
    RAG_DOCUMENT_PARSE_FAILED(446, "文档解析失败"),
    RAG_DOCUMENT_TOO_LARGE(447, "文档超过允许大小"),
    RAG_NO_RELEVANT_DOCUMENT(448, "没有检索到相关知识"),
    REDIS_UNAVAILABLE(450, "Redis 服务暂时不可用"),
    REDIS_OPERATION_TIMEOUT(451, "Redis 操作超时"),
    RABBITMQ_UNAVAILABLE(452, "RabbitMQ 服务暂时不可用"),
    RABBITMQ_PUBLISH_FAILED(453, "RabbitMQ 消息发布失败"),
    RABBITMQ_CONSUME_FAILED(454, "RabbitMQ 消息消费失败"),
    RABBITMQ_MESSAGE_INVALID(455, "RabbitMQ 消息格式不合法"),
    AGENT_SESSION_NOT_FOUND(460, "Agent 会话不存在"),
    AGENT_SESSION_CONCURRENCY_CONFLICT(461, "Agent 会话正在处理其他请求"),
    AGENT_SESSION_STATE_INVALID(462, "Agent 会话状态不合法"),
    AGENT_STATE_PERSISTENCE_FAILED(463, "Agent 状态保存失败"),
    AGENT_RUN_CANCELLED(464, "Agent 任务已取消"),
    AGENT_RUN_STEP_LIMIT_EXCEEDED(465, "Agent 执行轮数超过限制"),
    AGENT_RUN_DEADLINE_EXCEEDED(466, "Agent 执行超过截止时间"),
    AGENT_CONFIGURATION_INVALID(470, "Agent 配置不正确"),
    AGENT_PROMPT_NOT_FOUND(471, "Agent 提示词不存在"),
    AGENT_SKILL_NOT_FOUND(472, "Agent Skill 不存在"),
    AGENT_SKILL_CONFIGURATION_INVALID(473, "Agent Skill 配置不正确"),
    EXTERNAL_WEB_REQUEST_FAILED(474, "网页访问失败"),
    EXTERNAL_WEB_CONTENT_UNSAFE(475, "网页内容不安全"),
    RESUME_DOCUMENT_PARSE_FAILED(476, "简历文档解析失败"),
    RESUME_ANALYSIS_FAILED(477, "简历分析失败"),
    RESUME_ANALYSIS_NOT_FOUND(478, "简历分析结果不存在"),
    AGENT_INTERNAL_ERROR(499, "Agent 内部错误");

    private final int code;
    private final String description;

    ResultStatus(int code, String description) {
        this.code = code;
        this.description = description;
    }

    public int code() {
        return code;
    }

    public String description() {
        return description;
    }

    /** 根据整数状态码返回统一中文说明，未知状态按 Agent 内部错误处理。 */
    public static String descriptionOf(int code) {
        for (ResultStatus status : values()) {
            if (status.code == code) {
                return status.description;
            }
        }
        return AGENT_INTERNAL_ERROR.description;
    }

    public boolean isSuccess() {
        return code == SUCCESS_WITH_DATA.code || code == SUCCESS_WITHOUT_DATA.code;
    }
}
