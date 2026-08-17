CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag_knowledge_bases (knowledge_base_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'BUILDING', index_version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS rag_chunks (chunk_id TEXT PRIMARY KEY, knowledge_base_id TEXT NOT NULL REFERENCES rag_knowledge_bases(knowledge_base_id), document_id TEXT NOT NULL, index_version INTEGER NOT NULL, content_text TEXT NOT NULL, heading_path TEXT, page_number INTEGER, token_count INTEGER NOT NULL, embedding vector(1536), search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content_text)) STORED, kb_status TEXT NOT NULL DEFAULT 'READY');
CREATE TABLE IF NOT EXISTS rag_documents (document_id TEXT PRIMARY KEY, knowledge_base_id TEXT NOT NULL REFERENCES rag_knowledge_bases(knowledge_base_id), file_name TEXT NOT NULL, content_type TEXT, original_content BYTEA NOT NULL);
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS rag_chunks_search_idx ON rag_chunks USING GIN (search_vector);
