ALTER TABLE rag_index_job
    DROP CONSTRAINT IF EXISTS rag_index_job_status_check;

ALTER TABLE rag_index_job
    ADD CONSTRAINT rag_index_job_status_check
    CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED','FAILED_FINAL'));
