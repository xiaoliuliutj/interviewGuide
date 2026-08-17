CREATE TABLE IF NOT EXISTS agent_interview_workflow (
    session_id VARCHAR(64) PRIMARY KEY REFERENCES agent_session(session_id),
    user_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETING', 'COMPLETED', 'AUTO_TERMINATED', 'FAILED')),
    current_stage VARCHAR(32) NOT NULL,
    current_topic TEXT,
    state_json JSONB NOT NULL,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_interview_workflow_activity
    ON agent_interview_workflow(status, last_activity_at);

CREATE TABLE IF NOT EXISTS agent_interview_workflow_turn (
    turn_id UUID PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES agent_interview_workflow(session_id),
    run_id VARCHAR(64) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    topic TEXT,
    question TEXT NOT NULL,
    answer_masked TEXT NOT NULL,
    evaluation_json JSONB NOT NULL,
    action VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_interview_workflow_turn_session
    ON agent_interview_workflow_turn(session_id, created_at);

CREATE TABLE IF NOT EXISTS agent_resume_document (
    resume_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    file_name TEXT NOT NULL,
    content_type TEXT,
    raw_content BYTEA NOT NULL,
    extracted_text TEXT,
    content_hash VARCHAR(64) NOT NULL,
    target_role TEXT,
    status VARCHAR(32) NOT NULL CHECK (status IN ('UPLOADED', 'PARSING', 'ANALYZING', 'COMPLETED', 'FAILED')),
    evaluation_json JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_resume_document_user_status
    ON agent_resume_document(user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_resume_job (
    job_id UUID PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL UNIQUE,
    resume_id VARCHAR(64) NOT NULL REFERENCES agent_resume_document(resume_id),
    user_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    target_role TEXT,
    status VARCHAR(32) NOT NULL CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'FAILED_FINAL')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_resume_job_pending
    ON agent_resume_job(status, created_at);
