CREATE TABLE IF NOT EXISTS interview_session (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    resume_id VARCHAR(64) NOT NULL,
    target_role VARCHAR(255) NOT NULL,
    interview_direction VARCHAR(255),
    difficulty VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    state_version BIGINT NOT NULL DEFAULT 0,
    current_question TEXT,
    current_stage VARCHAR(64),
    current_topic TEXT,
    issued_question_count INTEGER NOT NULL DEFAULT 0,
    primary_question_count INTEGER NOT NULL DEFAULT 0,
    total_primary_question_count INTEGER NOT NULL DEFAULT 0,
    followup_count INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 20,
    final_evaluation_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_interview_session_user_status
    ON interview_session(user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS interview_turn (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES interview_session(session_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    stage VARCHAR(64),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    evaluation_summary TEXT,
    score INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, turn_index)
);
