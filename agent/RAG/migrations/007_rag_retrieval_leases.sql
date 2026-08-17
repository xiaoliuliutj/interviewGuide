CREATE TABLE IF NOT EXISTS rag_retrieval_lease (
    lease_id TEXT NOT NULL,
    knowledge_base_id TEXT NOT NULL REFERENCES rag_knowledge_bases(knowledge_base_id),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lease_id, knowledge_base_id)
);

CREATE INDEX IF NOT EXISTS rag_retrieval_lease_expiry_idx
    ON rag_retrieval_lease(knowledge_base_id, expires_at);
