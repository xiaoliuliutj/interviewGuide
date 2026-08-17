CREATE TABLE IF NOT EXISTS knowledge_base_delete_outbox (
    event_id VARCHAR(80) PRIMARY KEY,
    knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_base(id),
    user_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(80) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_kb_delete_outbox_pending
    ON knowledge_base_delete_outbox(status, next_attempt_at);
