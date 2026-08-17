ALTER TABLE rag_knowledge_bases
    ADD COLUMN IF NOT EXISTS knowledge_base_type TEXT NOT NULL DEFAULT 'USER';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rag_knowledge_base_type_check') THEN
        ALTER TABLE rag_knowledge_bases
            ADD CONSTRAINT rag_knowledge_base_type_check
            CHECK (knowledge_base_type IN ('USER', 'SYSTEM'));
    END IF;
END $$;
ALTER TABLE rag_chunks
    ADD COLUMN IF NOT EXISTS lexical_terms TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
CREATE INDEX IF NOT EXISTS rag_chunks_lexical_terms_idx
    ON rag_chunks USING GIN (lexical_terms);
