-- Adds an original-title companion index for strict title search.
-- This keeps localized/original title lookup aligned with the existing
-- case-insensitive display-title search index.

CREATE INDEX IF NOT EXISTS idx_content_original_title_lower
ON content (LOWER(original_title));
