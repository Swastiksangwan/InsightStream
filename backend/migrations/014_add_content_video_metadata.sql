-- Adds normalized title video metadata, one global primary selection, and fetch state.

CREATE TABLE IF NOT EXISTS content_videos (
    id BIGSERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL DEFAULT 'tmdb',
    source_video_id VARCHAR(255) NOT NULL,
    site VARCHAR(50) NOT NULL,
    video_type VARCHAR(50),
    name TEXT,
    official BOOLEAN,
    language_code VARCHAR(16),
    country_code VARCHAR(16),
    published_at TIMESTAMPTZ,
    size INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_content_videos_source_identity
        UNIQUE (content_id, source, site, source_video_id),
    CONSTRAINT uq_content_videos_content_id_id UNIQUE (content_id, id),
    CONSTRAINT chk_content_videos_size CHECK (size IS NULL OR size >= 0)
);

CREATE TABLE IF NOT EXISTS content_primary_videos (
    content_id INTEGER PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    content_video_id BIGINT NOT NULL UNIQUE,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_content_primary_videos_owned_video
        FOREIGN KEY (content_id, content_video_id)
        REFERENCES content_videos(content_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_video_fetch_state (
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL,
    last_attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_fetched_at TIMESTAMPTZ,
    last_fetch_status VARCHAR(20) NOT NULL CHECK (
        last_fetch_status IN ('success', 'empty', 'failed', 'incomplete')
    ),
    last_fetch_error TEXT,
    source_snapshot_empty BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, source),
    CONSTRAINT chk_content_video_fetch_state_empty_status CHECK (
        (last_fetch_status = 'empty' AND source_snapshot_empty)
        OR (last_fetch_status <> 'empty' AND NOT source_snapshot_empty)
    )
);

-- Harden databases where the first local draft of migration 014 was already run.
ALTER TABLE content_video_fetch_state
ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ;

UPDATE content_video_fetch_state
SET last_attempted_at = COALESCE(last_attempted_at, last_fetched_at, updated_at, NOW())
WHERE last_attempted_at IS NULL;

ALTER TABLE content_video_fetch_state
ALTER COLUMN last_attempted_at SET DEFAULT NOW(),
ALTER COLUMN last_attempted_at SET NOT NULL,
ALTER COLUMN last_fetched_at DROP NOT NULL;

UPDATE content_video_fetch_state
SET source_snapshot_empty = (last_fetch_status = 'empty')
WHERE source_snapshot_empty IS DISTINCT FROM (last_fetch_status = 'empty');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'content_video_fetch_state'::regclass
          AND conname = 'chk_content_video_fetch_state_empty_status'
    ) THEN
        ALTER TABLE content_video_fetch_state
        ADD CONSTRAINT chk_content_video_fetch_state_empty_status CHECK (
            (last_fetch_status = 'empty' AND source_snapshot_empty)
            OR (last_fetch_status <> 'empty' AND NOT source_snapshot_empty)
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'content_videos'::regclass
          AND conname = 'uq_content_videos_content_id_id'
    ) THEN
        ALTER TABLE content_videos
        ADD CONSTRAINT uq_content_videos_content_id_id UNIQUE (content_id, id);
    END IF;
END $$;

ALTER TABLE content_primary_videos
DROP CONSTRAINT IF EXISTS content_primary_videos_content_video_id_fkey;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'content_primary_videos'::regclass
          AND conname = 'fk_content_primary_videos_owned_video'
    ) THEN
        ALTER TABLE content_primary_videos
        ADD CONSTRAINT fk_content_primary_videos_owned_video
        FOREIGN KEY (content_id, content_video_id)
        REFERENCES content_videos(content_id, id) ON DELETE CASCADE;
    END IF;
END $$;

DROP INDEX IF EXISTS idx_content_videos_content_id;
DROP INDEX IF EXISTS idx_content_videos_content_source;
DROP INDEX IF EXISTS idx_content_video_fetch_state_status;
