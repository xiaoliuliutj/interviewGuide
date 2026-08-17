CREATE TABLE IF NOT EXISTS agent_session (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    resume_id VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    active_run_id VARCHAR(64),
    active_run_heartbeat_at TIMESTAMPTZ,
    state_version BIGINT NOT NULL DEFAULT 0,
    summary_version BIGINT NOT NULL DEFAULT 0,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_run (
    run_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES agent_session(session_id),
    user_id VARCHAR(64) NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    expected_state_version BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('PROCESSING', 'COMPLETED', 'FAILED')),
    result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_run_session_status
    ON agent_run (session_id, status);

CREATE INDEX IF NOT EXISTS idx_agent_session_user_id
    ON agent_session (user_id);

CREATE TABLE IF NOT EXISTS agent_session_message (
    message_id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES agent_session(session_id),
    run_id VARCHAR(64) NOT NULL,
    turn_number INTEGER NOT NULL,
    sequence_number BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content_masked TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, sequence_number),
    UNIQUE (session_id, run_id, role)
);

CREATE TABLE IF NOT EXISTS agent_session_summary (
    summary_id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES agent_session(session_id),
    version BIGINT NOT NULL,
    summarized_until_sequence BIGINT NOT NULL,
    summary_content TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('READY', 'PENDING', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, version)
);

CREATE TABLE IF NOT EXISTS agent_user_profile_memory (
    memory_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    version BIGINT NOT NULL,
    content_json JSONB NOT NULL,
    summary_text TEXT,
    source VARCHAR(32) NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_user_profile_current
    ON agent_user_profile_memory (user_id)
    WHERE is_current AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS agent_resume_memory (
    memory_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    resume_id VARCHAR(64) NOT NULL,
    version BIGINT NOT NULL,
    content_json JSONB NOT NULL,
    summary_text TEXT,
    source VARCHAR(32) NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, resume_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_resume_memory_current
    ON agent_resume_memory (user_id, resume_id)
    WHERE is_current AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS agent_interview_memory (
    memory_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL REFERENCES agent_session(session_id),
    content_json JSONB NOT NULL,
    summary_text TEXT NOT NULL,
    source VARCHAR(32) NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, session_id)
);

CREATE TABLE IF NOT EXISTS agent_user_interview_overview (
    memory_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    version BIGINT NOT NULL,
    content_json JSONB NOT NULL,
    summary_text TEXT NOT NULL,
    source VARCHAR(32) NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, version)
);

CREATE TABLE IF NOT EXISTS agent_outbox_event (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    claimed_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);

ALTER TABLE agent_outbox_event ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
ALTER TABLE agent_outbox_event ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE agent_session ADD COLUMN IF NOT EXISTS active_run_heartbeat_at TIMESTAMPTZ;
