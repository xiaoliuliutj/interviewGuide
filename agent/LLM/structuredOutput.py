"""参考项目同款：提示词约束、JSON 解析、Pydantic 校验和格式纠错重试。"""

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from agent.Common.Exceptions.AgentException import LlmOutputSchemaError
from agent.Common.PromptService import PromptLoader
from agent.LLM.llmService import LlmService


T = TypeVar("T", bound=BaseModel)


class StructuredOutputInvoker:
    """Agent 持有业务 Schema；调用方只接收已校验的结构化结果。"""

    def __init__(self, llmService: LlmService, promptLoader: PromptLoader | None = None) -> None:
        self.llmService = llmService
        self.promptLoader = promptLoader or PromptLoader()

    async def invoke(
        self,
        *,
        schema: type[T],
        businessPrompt: str,
        inputPayload: dict[str, object],
    ) -> T:
        fewShotOutput = self._fewShotOutput(schema)
        formatPrompt = self.promptLoader.loadPrompt(
            "Shared/structuredOutput.txt",
            schemaJson=json.dumps(schema.model_json_schema(by_alias=True), ensure_ascii=False),
            fewShotSection=(
                "\n合法格式示例：\n\n" + json.dumps(fewShotOutput, ensure_ascii=False)
                if fewShotOutput else ""
            ),
        )
        messages = [
            {"role": "system", "content": f"{businessPrompt}\n\n{formatPrompt}"},
            {"role": "user", "content": json.dumps(inputPayload, ensure_ascii=False, default=str)},
        ]
        lastError: Exception | None = None
        for correctionAttempt in range(3):
            content = await self.llmService.requestCompletion(messages, temperature=0, jsonMode=True)
            try:
                payload = self._parseJsonObject(content)
                return schema.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
                lastError = error
                if correctionAttempt == 2:
                    break
                messages.extend([
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": (
                        "上一轮输出未通过程序校验。请只修复并返回完整 JSON 对象，"
                        "不要 Markdown、解释或未定义字段。校验原因："
                        + self._readableError(error)
                    )},
                ])
        raise LlmOutputSchemaError(
            f"模型连续 3 次未返回符合 {schema.__name__} 的 JSON：{self._readableError(lastError)}"
        ) from lastError

    @staticmethod
    def _parseJsonObject(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("模型输出根节点必须是 JSON 对象")
        return payload

    @staticmethod
    def _readableError(error: Exception | None) -> str:
        if isinstance(error, ValidationError):
            fields = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
            return "字段校验失败: " + ", ".join(fields[:8])
        return (str(error).replace("\n", " ")[:500] if error else "未知错误")

    @staticmethod
    def _fewShotOutput(schema: type[BaseModel]) -> dict[str, Any]:
        if schema.__name__ == "ResumeEvaluation":
            return {
                "overallScore": 75, "contentScore": 76, "structureScore": 78,
                "skillMatchScore": 74, "expressionScore": 72, "projectScore": 75,
                "summary": "经历与目标岗位基本匹配，但仍可补充可验证的量化成果。",
                "strengths": ["项目描述清晰"], "suggestions": ["补充量化结果"],
                "issues": [{"question": "项目职责边界不够具体", "priority": "MEDIUM", "suggestion": "补充个人职责和成果"}],
                "technicalStack": ["Java"], "technicalDepth": ["具备项目实践"],
                "careerPreferences": ["后端开发"],
            }
        return {}
