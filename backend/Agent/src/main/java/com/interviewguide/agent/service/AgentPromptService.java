package com.interviewguide.agent.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.core.io.ClassPathResource;

/**
 * 读取并填充 Java 发送给 Agent 的用户提示词模板。
 *
 * <p>业务 Service 选择模板并提供变量；该类不理解简历、知识库或面试的业务含义。
 * 模板集中存放能够避免自然语言指令散落在 Java 代码中。</p>
 */
public class AgentPromptService {
    /**
     * 读取指定模板并替换形如 {{name}} 的变量。
     *
     * <p>未提供的变量保留原占位符，便于在开发和联调阶段直接发现模板与调用方不一致。</p>
     */
    public String render(String templateName, Map<String, ?> variables) {
        ClassPathResource resource = new ClassPathResource("Prompts/" + templateName);
        try (InputStream stream = resource.getInputStream()) {
            String content = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            for (Map.Entry<String, ?> entry : variables.entrySet()) {
                content = content.replace("{{" + entry.getKey() + "}}", String.valueOf(entry.getValue()));
            }
            return content;
        } catch (IOException error) {
            throw new IllegalStateException("未找到 Agent 提示词模板：" + templateName, error);
        }
    }
}
