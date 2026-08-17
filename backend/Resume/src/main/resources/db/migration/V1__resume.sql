CREATE TABLE IF NOT EXISTS resume (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128),
    file_size BIGINT NOT NULL,
    target_role VARCHAR(255),
    status VARCHAR(32) NOT NULL,
    agent_run_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_resume_user_updated ON resume(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS resume_analysis (
    id VARCHAR(64) PRIMARY KEY,
    resume_id VARCHAR(64) NOT NULL UNIQUE REFERENCES resume(id),
    status VARCHAR(32) NOT NULL,
    evaluation_json JSONB,
    error_message TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
