-- ============================================================
-- InsightStream Manual Migration
-- 011_add_content_original_title_language.sql
--
-- Purpose:
-- Store provider-backed original title and original language code
-- for content detail display. This does not infer dubbed-language
-- availability and is safe to run more than once.
-- ============================================================

ALTER TABLE content
ADD COLUMN IF NOT EXISTS original_title TEXT;

ALTER TABLE content
ADD COLUMN IF NOT EXISTS original_language VARCHAR(16);
