ALTER TABLE agent_resume_job
    ADD COLUMN IF NOT EXISTS output_schema JSONB;

ALTER TABLE agent_resume_job
    ADD COLUMN IF NOT EXISTS output_prompt TEXT;
