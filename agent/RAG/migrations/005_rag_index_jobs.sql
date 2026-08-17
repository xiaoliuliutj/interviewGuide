CREATE TABLE IF NOT EXISTS rag_index_job (
    job_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    knowledge_base_id TEXT NOT NULL REFERENCES rag_knowledge_bases(knowledge_base_id),
    document_id TEXT NOT NULL REFERENCES rag_documents(document_id),
    user_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS rag_index_job_ready_idx ON rag_index_job(status, next_attempt_at);
