from dataclasses import dataclass
from enum import StrEnum


class KnowledgeBaseStatus(StrEnum):
    BUILDING = "BUILDING"
    READY = "READY"
    DELETE_REQUESTED = "DELETE_REQUESTED"
    DELETING = "DELETING"
    DELETED = "DELETED"
    DELETE_FAILED = "DELETE_FAILED"


@dataclass(frozen=True)
class DocumentChunk:
    chunkId: str
    knowledgeBaseId: str
    documentId: str
    content: str
    headingPath: str | None
    pageNumber: int | None
    tokenCount: int
    indexVersion: int
    lexicalTerms: tuple[str, ...]


@dataclass(frozen=True)
class RagSearchResult:
    chunk: DocumentChunk
    vectorRank: int
    textRank: int
    rrfScore: float


@dataclass(frozen=True)
class RagAccessScope:
    knowledgeBaseIds: tuple[str, ...]
    indexVersions: tuple[int, ...]
