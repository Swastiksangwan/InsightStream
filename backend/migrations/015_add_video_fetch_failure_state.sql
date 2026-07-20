-- Preserve retry disposition and bound repeated video refresh failures.

ALTER TABLE content_video_fetch_state
ADD COLUMN IF NOT EXISTS last_fetch_retryable BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS last_failure_class VARCHAR(50),
ADD COLUMN IF NOT EXISTS consecutive_failure_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE content_video_fetch_state
DROP CONSTRAINT IF EXISTS chk_content_video_fetch_state_failure_count;

ALTER TABLE content_video_fetch_state
ADD CONSTRAINT chk_content_video_fetch_state_failure_count CHECK (
    consecutive_failure_count >= 0
);

-- Existing failures did not record enough information to retry safely.
UPDATE content_video_fetch_state
SET last_fetch_retryable = FALSE,
    last_failure_class = CASE
        WHEN last_fetch_status IN ('failed', 'incomplete')
        THEN COALESCE(last_failure_class, 'legacy_unclassified')
        ELSE NULL
    END,
    consecutive_failure_count = CASE
        WHEN last_fetch_status IN ('failed', 'incomplete')
        THEN GREATEST(consecutive_failure_count, 1)
        ELSE 0
    END;

ALTER TABLE content_video_fetch_state
DROP CONSTRAINT IF EXISTS chk_content_video_fetch_state_failure_details;

ALTER TABLE content_video_fetch_state
ADD CONSTRAINT chk_content_video_fetch_state_failure_details CHECK (
    (
        last_fetch_status IN ('success', 'empty')
        AND NOT last_fetch_retryable
        AND last_failure_class IS NULL
        AND consecutive_failure_count = 0
    )
    OR (
        last_fetch_status IN ('failed', 'incomplete')
        AND last_failure_class IS NOT NULL
        AND consecutive_failure_count >= 1
    )
);
