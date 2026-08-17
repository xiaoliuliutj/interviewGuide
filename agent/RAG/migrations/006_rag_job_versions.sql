ALTER TABLE rag_index_job
    ADD COLUMN IF NOT EXISTS index_version INTEGER;

UPDATE rag_index_job j
SET index_version = k.index_version
FROM rag_knowledge_bases k
WHERE j.knowledge_base_id = k.knowledge_base_id
  AND j.index_version IS NULL;

ALTER TABLE rag_index_job
    ALTER COLUMN index_version SET NOT NULL;

CREATE INDEX IF NOT EXISTS rag_index_job_version_idx
    ON rag_index_job(knowledge_base_id, index_version, status);
