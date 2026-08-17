CREATE TABLE IF NOT EXISTS agent_rag_retrieval_source (
    source_id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    knowledge_base_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    heading_path TEXT,
    page_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, run_id, chunk_id)
);
