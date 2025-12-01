-- ============================================
-- Media Tracking Enhancement Migration
-- ============================================
-- Adds columns for MD5 checksums, S3 archive URLs,
-- enhanced AI analysis status tracking, and detailed logging
-- ============================================

-- Add MD5 checksum column for file integrity verification
ALTER TABLE post_media ADD COLUMN IF NOT EXISTS md5_sum TEXT;

-- Add S3 archive URL column for cloud storage reference
ALTER TABLE post_media ADD COLUMN IF NOT EXISTS archive_url TEXT;

-- Update ai_analysis_status to use enum-like constraint
-- First, drop existing constraint if it exists
ALTER TABLE post_media
  DROP CONSTRAINT IF EXISTS post_media_ai_analysis_status_check;

-- Add new constraint with proper status values
ALTER TABLE post_media
  ADD CONSTRAINT post_media_ai_analysis_status_check
  CHECK (ai_analysis_status IN ('not_started', 'started', 'completed', 'failed', 'pending'));

-- Update default value for ai_analysis_status to 'not_started'
-- Note: 'pending' is kept in the constraint for backward compatibility with existing rows
ALTER TABLE post_media
  ALTER COLUMN ai_analysis_status SET DEFAULT 'not_started';

-- Add ai_analysis_log column for detailed logging
ALTER TABLE post_media ADD COLUMN IF NOT EXISTS ai_analysis_log JSONB;

-- Update column comments
COMMENT ON COLUMN post_media.md5_sum IS 'MD5 checksum of the media file for integrity verification and deduplication';
COMMENT ON COLUMN post_media.archive_url IS 'S3 URL for archived copy of media file';
COMMENT ON COLUMN post_media.ai_analysis_status IS 'AI analysis status: not_started, started, completed, failed';
COMMENT ON COLUMN post_media.ai_analysis_log IS 'Detailed JSONB log of AI analysis attempts, results, and events';

-- Add index for MD5 lookups (enables fast deduplication)
CREATE INDEX IF NOT EXISTS idx_media_md5_sum ON post_media(md5_sum);

-- Add index for archive status tracking (only index non-null values)
CREATE INDEX IF NOT EXISTS idx_media_archive_url ON post_media(archive_url) WHERE archive_url IS NOT NULL;

-- Add composite index for AI analysis queue queries
CREATE INDEX IF NOT EXISTS idx_media_ai_status_created ON post_media(ai_analysis_status, created_at) WHERE ai_analysis_status IN ('not_started', 'started');

-- Update existing rows to use new default status if they have 'pending'
UPDATE post_media
SET ai_analysis_status = 'not_started'
WHERE ai_analysis_status = 'pending';

-- Initialize ai_analysis_log for existing rows with empty JSON array
UPDATE post_media
SET ai_analysis_log = '[]'::jsonb
WHERE ai_analysis_log IS NULL;

-- Add comment on the table itself to document the enhancement
COMMENT ON TABLE post_media IS 'Media attachments with AI analysis, local cache, and S3 archive tracking';
