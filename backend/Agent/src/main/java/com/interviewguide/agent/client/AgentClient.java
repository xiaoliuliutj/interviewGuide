package com.interviewguide.agent.client;

import com.interviewguide.agent.dto.AgentHealthResponse;
import com.interviewguide.agent.dto.AgentOperationRequest;
import com.interviewguide.agent.dto.AgentOperationResponse;

/**
 * Java 与独立 Agent 之间唯一的通用通信边界。
 * Java 业务模块不依赖 Agent 内部任务枚举和实现类。
 */
public interface AgentClient {
    AgentHealthResponse health();

    /**
     * 提交一次对话或确定性能力请求。
     * 请求的 mode 和 capability 由 Agent 协议解释，Java 只负责组织 prompt/data。
     */
    AgentOperationResponse execute(AgentOperationRequest request);
}
