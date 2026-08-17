CREATE TABLE IF NOT EXISTS rag_web_crawl_job (
    crawl_token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entry_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'PARTIAL_COMPLETED', 'FAILED')),
    stop_reason TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS rag_web_crawl_job_owner_expiry_idx
    ON rag_web_crawl_job(user_id, expires_at);

CREATE TABLE IF NOT EXISTS rag_web_crawl_page (
    crawl_token TEXT NOT NULL REFERENCES rag_web_crawl_job(crawl_token) ON DELETE CASCADE,
    page_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    content_type TEXT,
    markdown TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    depth INTEGER NOT NULL,
    parent_url TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (crawl_token, page_id),
    UNIQUE (crawl_token, url)
);

CREATE TABLE IF NOT EXISTS rag_web_crawl_import (
    import_run_id TEXT PRIMARY KEY,
    crawl_token TEXT NOT NULL REFERENCES rag_web_crawl_job(crawl_token) ON DELETE RESTRICT,
    user_id TEXT NOT NULL,
    selected_page_ids JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROCESSING', 'COMPLETED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS rag_web_crawl_import_page (
    import_run_id TEXT NOT NULL REFERENCES rag_web_crawl_import(import_run_id) ON DELETE CASCADE,
    page_id TEXT NOT NULL,
    knowledge_base_id TEXT NOT NULL UNIQUE,
    document_id TEXT NOT NULL UNIQUE,
    index_run_id TEXT NOT NULL UNIQUE,
    PRIMARY KEY (import_run_id, page_id)
);
