CREATE UNIQUE INDEX IF NOT EXISTS uq_interview_session_one_unfinished_per_user
    ON interview_session(user_id)
    WHERE status IN ('CREATING', 'ACTIVE', 'PAUSED');
