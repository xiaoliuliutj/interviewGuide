-- 数据库初始化脚本
-- 此脚本在 PostgreSQL 容器首次启动时自动执行
-- 包含所有模块的表结构（Interview、Resume、KnowledgeBase）

-- ============================================
-- Resume 模块
-- ============================================
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
    resume_id VARCHAR(64) NOT NULL UNIQUE REFERENCES resume(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL,
    evaluation_json JSONB,
    error_message TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resume_delete_outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    resume_id VARCHAR(64) NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
    user_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_resume_delete_active
    ON resume_delete_outbox(resume_id) WHERE status IN ('PENDING','PROCESSING','FAILED');

-- ============================================
-- Interview 模块
-- ============================================
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_interview_session_one_unfinished_per_user
    ON interview_session(user_id)
    WHERE status IN ('CREATING', 'ACTIVE', 'PAUSED');

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

CREATE TABLE IF NOT EXISTS interview_close_outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES interview_session(session_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_interview_close_active
    ON interview_close_outbox(session_id) WHERE status IN ('PENDING','PROCESSING','FAILED');

-- ============================================
-- KnowledgeBase 模块
-- ============================================
CREATE TABLE IF NOT EXISTS knowledge_base (
    id BIGSERIAL PRIMARY KEY,
    agent_knowledge_base_id VARCHAR(80) NOT NULL UNIQUE,
    agent_document_id VARCHAR(80) NOT NULL,
    owner_user_id VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(128),
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128),
    source_url TEXT,
    source_title VARCHAR(255),
    source_fetched_at TIMESTAMP WITH TIME ZONE,
    source_hash VARCHAR(255),
    file_size BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    vector_error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_owner_status
    ON knowledge_base(owner_user_id, status);

CREATE OR REPLACE FUNCTION update_knowledge_base_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_knowledge_base_updated_at ON knowledge_base;
CREATE TRIGGER trg_knowledge_base_updated_at
    BEFORE UPDATE ON knowledge_base
    FOR EACH ROW EXECUTE FUNCTION update_knowledge_base_updated_at();

CREATE TABLE IF NOT EXISTS knowledge_base_delete_outbox (
    event_id VARCHAR(80) PRIMARY KEY,
    knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_base(id),
    user_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(80) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    claimed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_kb_delete_outbox_pending
    ON knowledge_base_delete_outbox(status, next_attempt_at);

