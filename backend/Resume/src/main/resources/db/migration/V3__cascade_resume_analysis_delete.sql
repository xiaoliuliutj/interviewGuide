ALTER TABLE resume_analysis DROP CONSTRAINT IF EXISTS resume_analysis_resume_id_fkey;
ALTER TABLE resume_analysis
    ADD CONSTRAINT resume_analysis_resume_id_fkey
    FOREIGN KEY (resume_id) REFERENCES resume(id) ON DELETE CASCADE;
