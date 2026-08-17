import base64
from typing import Any

from agent.Common.AgentModels import AgentContext
from agent.Common.Exceptions.AgentException import ToolArgumentError
from agent.RAG.ragDocumentParser import DocumentParser


class ToolsDocumentParser:
    """提供模型按需调用的文档解析工具。"""

    async def parseDocument(self, arguments: dict[str, Any], _: AgentContext) -> dict[str, Any]:
        """解析 Base64 或文本形式的文档，并保留标题路径与页码信息。"""
        content = arguments.get("content")
        fileName = arguments.get("fileName")
        if not isinstance(content, str) or not isinstance(fileName, str) or not fileName.strip():
            raise ToolArgumentError("parseDocument 需要 content 和 fileName")
        try:
            raw = base64.b64decode(content) if arguments.get("contentEncoding") == "base64" else content.encode("utf-8")
        except Exception as error:
            raise ToolArgumentError("parseDocument 的 Base64 内容无效") from error
        sections = DocumentParser().parse(raw, fileName, arguments.get("contentType"))
        return {"sections": [{"content": item.content, "headingPath": item.headingPath, "pageNumber": item.pageNumber} for item in sections]}
