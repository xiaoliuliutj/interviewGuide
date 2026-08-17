from dataclasses import dataclass


@dataclass(frozen=True)
class RagPolicy:
    chunkSizeTokens: int = 800
    chunkOverlapTokens: int = 96
    embeddingBatchSize: int = 10
    topK: int = 8
    candidateMultiplier: int = 3
    minCosineSimilarity: float = 0.35
    cacheTtlSeconds: int = 1800
    maxDocumentBytes: int = 20 * 1024 * 1024
    webCrawlPreviewTtlSeconds: int = 24 * 60 * 60
