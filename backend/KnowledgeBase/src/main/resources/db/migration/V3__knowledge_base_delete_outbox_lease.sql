ALTER TABLE knowledge_base_delete_outbox
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP WITH TIME ZONE;
