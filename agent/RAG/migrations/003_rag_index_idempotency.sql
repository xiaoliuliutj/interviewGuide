ALTER TABLE rag_knowledge_bases
    ADD COLUMN IF NOT EXISTS last_index_run_id TEXT,
    ADD COLUMN IF NOT EXISTS last_document_id TEXT,
    ADD COLUMN IF NOT EXISTS last_chunk_count INTEGER;
