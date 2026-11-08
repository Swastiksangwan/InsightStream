-- insightstream-migration: transactional
-- No backfill: legacy import timestamps are not verified collection evidence.
CREATE TABLE public.content_series_fetch_state (
    content_id integer PRIMARY KEY REFERENCES public.content(id),
    last_attempted_at timestamptz NOT NULL,
    last_source_fetched_at timestamptz,
    last_source_origin text CHECK (last_source_origin IN ('fetched', 'reused')),
    last_request_signature text,
    last_successful_at timestamptz,
    last_applied_at timestamptz,
    last_changed_at timestamptz,
    change_source_at timestamptz,
    last_status text NOT NULL CHECK (last_status IN ('started', 'success', 'failed', 'incomplete')),
    last_error text,
    retryable boolean NOT NULL DEFAULT false,
    failure_class text,
    consecutive_failure_count integer NOT NULL DEFAULT 0 CHECK (consecutive_failure_count >= 0),
    CHECK (last_request_signature IS NULL OR last_request_signature ~ '^[0-9a-f]{64}$'),
    CHECK (last_status <> 'success' OR (last_successful_at IS NOT NULL AND last_applied_at IS NOT NULL
        AND last_source_fetched_at IS NOT NULL AND last_source_origin IS NOT NULL
        AND last_request_signature IS NOT NULL AND NOT retryable
        AND failure_class IS NULL AND consecutive_failure_count = 0))
);
