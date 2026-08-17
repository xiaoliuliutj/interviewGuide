from uuid import uuid4

from agent.RAG.ragDocumentParser import ParsedSection
from agent.RAG.ragModels import DocumentChunk
from agent.RAG.ragPolicy import RagPolicy


class TokenChunker:
    """按 token 窗口切分 section，使用重叠窗口避免上下文在边界丢失。"""

    def __init__(self, policy: RagPolicy | None = None) -> None:
        self.policy = policy or RagPolicy()
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.encoder = None

    def split(self, sections: list[ParsedSection], knowledgeBaseId: str, documentId: str, indexVersion: int = 1) -> list[DocumentChunk]:
        """为每个 section 生成稳定顺序的 chunk，并保留来源元数据。"""
        result: list[DocumentChunk] = []
        for section in sections:
            tokens = self.encode(section.content)
            if not tokens:
                continue
            start = 0
            while start < len(tokens):
                end = min(start + self.policy.chunkSizeTokens, len(tokens))
                text = self.decode(tokens[start:end]).strip()
                if text:
                    result.append(DocumentChunk(str(uuid4()), knowledgeBaseId, documentId, text,
                                                 section.headingPath, section.pageNumber, end - start,
                                                 indexVersion, tuple(str(token) for token in tokens[start:end])))
                if end >= len(tokens):
                    break
                start = max(end - self.policy.chunkOverlapTokens, start + 1)
        return result

    def encode(self, text: str) -> list[int]:
        if self.encoder is not None:
            return self.encoder.encode(text)
        return text.split()

    def decode(self, tokens: list[int]) -> str:
        if self.encoder is not None:
            return self.encoder.decode(tokens)
        return " ".join(tokens)
