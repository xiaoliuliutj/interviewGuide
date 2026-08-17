from agent.RAG.ragChunker import TokenChunker
from agent.RAG.ragDocumentParser import DocumentParser
from agent.RAG.ragPolicy import RagPolicy
from agent.RAG.ragCache import RagSessionCache
from agent.RAG.ragRepository import RagRepository


def test_markdown_sections_keep_heading_path():
    sections = DocumentParser().parseMarkdown("# Java\nintro\n## Spring\ncontent")
    assert len(sections) == 2
    assert sections[0].headingPath == "Java"
    assert sections[1].headingPath == "Java / Spring"


def test_token_chunker_applies_overlap():
    policy = RagPolicy(chunkSizeTokens=5, chunkOverlapTokens=1)
    chunks = TokenChunker(policy).split(
        DocumentParser().parseMarkdown("# Title\n" + " ".join(f"word{i}" for i in range(12))),
        "kb",
        "doc",
    )
    assert len(chunks) >= 3
    assert chunks[0].tokenCount <= 5


def test_empty_document_produces_no_indexable_chunks():
    chunks = TokenChunker().split(
        DocumentParser().parseMarkdown("   "),
        "kb",
        "doc",
    )
    assert chunks == []


def test_cosine_similarity_is_used_for_cache_threshold():
    cache = RagSessionCache(None)  # type: ignore[arg-type]
    assert cache.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cache.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_bm25_ranking_prefers_repeated_query_terms():
    repository = RagRepository(None)  # type: ignore[arg-type]
    rows = [
        {"lexical_terms": ["java", "java", "spring"], "token_count": 3, "chunk_id": "1"},
        {"lexical_terms": ["java", "database"], "token_count": 2, "chunk_id": "2"},
    ]
    ranked = repository.rankBm25(rows, rows, ["java", "spring"])
    assert ranked[0]["chunk_id"] == "1"
