# Media Handling Enhancement Specification

## Overview
This specification defines enhancements to the media handling system in social-tui to improve media tracking, storage, and AI analysis capabilities.

## Current State

### Existing Infrastructure
- **Table**: `post_media` (defined in `supabase/migrations/20251130223349_create_schema.sql:186-210`)
- **Cache Directory**: `./cache/images/` (used by `interactive_posts.py:28-29`)
- **Current Columns**:
  - `media_id` (TEXT PRIMARY KEY)
  - `post_id` (TEXT NOT NULL, FK to posts)
  - `media_type` (TEXT NOT NULL)
  - `media_url` (TEXT NOT NULL)
  - `local_file_path` (TEXT)
  - `file_size` (INTEGER)
  - `mime_type` (TEXT)
  - `width` (INTEGER)
  - `height` (INTEGER)
  - `ai_analysis_status` (TEXT DEFAULT 'pending')
  - `ai_analysis` (TEXT)
  - `ai_analyzed_at` (TIMESTAMPTZ)
  - `created_at` (TIMESTAMPTZ DEFAULT NOW())
  - `updated_at` (TIMESTAMPTZ DEFAULT NOW())

### Current Media Handling in Code
- **Image Caching**: `interactive_posts.py:47-136` implements MD5-based caching for images
  - `get_cached_image_path()` generates cache file paths using MD5 hash of URL
  - `download_image()` downloads with proper User-Agent headers
  - `get_image_data()` checks cache before downloading
  - Cache location: `./cache/images/`
  - Cache filename format: `{md5_hash}.{extension}`

## Required Enhancements

### 1. Database Schema Changes

#### Migration: `add_media_tracking_columns.sql`

```sql
-- Add MD5 checksum column for file integrity verification
ALTER TABLE post_media ADD COLUMN md5_sum TEXT;

-- Add S3 archive URL column for cloud storage reference
ALTER TABLE post_media ADD COLUMN archive_url TEXT;

-- Update ai_analysis_status to use enum-like constraint
ALTER TABLE post_media
  DROP CONSTRAINT IF EXISTS post_media_ai_analysis_status_check;

ALTER TABLE post_media
  ADD CONSTRAINT post_media_ai_analysis_status_check
  CHECK (ai_analysis_status IN ('not_started', 'started', 'completed', 'failed'));

-- Change default value for ai_analysis_status
ALTER TABLE post_media
  ALTER COLUMN ai_analysis_status SET DEFAULT 'not_started';

-- Add ai_analysis_log column for detailed logging
ALTER TABLE post_media ADD COLUMN ai_analysis_log JSONB;

-- Update comments
COMMENT ON COLUMN post_media.md5_sum IS 'MD5 checksum of the media file for integrity verification';
COMMENT ON COLUMN post_media.archive_url IS 'S3 URL for archived copy of media';
COMMENT ON COLUMN post_media.ai_analysis_status IS 'Status: not_started, started, completed, failed';
COMMENT ON COLUMN post_media.ai_analysis_log IS 'Detailed log of AI analysis attempts and results';

-- Add index for MD5 lookups (deduplication)
CREATE INDEX idx_media_md5_sum ON post_media(md5_sum);

-- Add index for archive status tracking
CREATE INDEX idx_media_archive_url ON post_media(archive_url) WHERE archive_url IS NOT NULL;
```

### 2. Local Media Storage System

#### Directory Structure
```
./cache/
  └── media/
      ├── images/      # Image files (already exists)
      ├── videos/      # Video files
      └── documents/   # Document files
```

#### File Naming Convention
- **Format**: `{md5_sum}.{extension}`
- **Example**: `a1b2c3d4e5f6789012345678901234.jpg`
- **Benefits**:
  - Automatic deduplication by content
  - URL-independent storage
  - Fast integrity verification

#### Cache Management Module: `media_cache.py`

Create new module with the following functions:

```python
def get_media_cache_path(media_type: str, md5_sum: str, extension: str) -> Path:
    """Get the local cache path for media file."""

def download_and_cache_media(media_url: str, media_type: str) -> dict:
    """
    Download media from URL, calculate MD5, and cache locally.

    Returns:
        {
            'md5_sum': str,
            'local_path': Path,
            'file_size': int,
            'mime_type': str,
            'width': int | None,
            'height': int | None
        }
    """

def verify_cached_media(local_path: Path, expected_md5: str) -> bool:
    """Verify integrity of cached media file."""

def calculate_md5(file_path: Path) -> str:
    """Calculate MD5 checksum of file."""
```

### 3. S3 Archive Integration

#### Configuration
- Add to `.env`:
  ```
  AWS_S3_BUCKET=social-tui-media
  AWS_S3_REGION=us-east-1
  AWS_ACCESS_KEY_ID=...
  AWS_SECRET_ACCESS_KEY=...
  ```

#### Archive Module: `media_archive.py`

```python
def upload_to_s3(local_path: Path, media_id: str) -> str:
    """
    Upload media file to S3.

    Args:
        local_path: Path to local media file
        media_id: post_media.media_id

    Returns:
        S3 URL for the uploaded file
    """

def generate_s3_key(media_id: str, extension: str) -> str:
    """Generate S3 object key: media/{year}/{month}/{media_id}.{ext}"""

def verify_s3_upload(s3_url: str, expected_md5: str) -> bool:
    """Verify S3 object matches expected MD5."""
```

### 4. Media Extraction and Population

#### Update `manage_data.py`

Add new function after `import_directory()`:

```python
def extract_and_store_media(client, post_id: str, post_data: dict) -> list:
    """
    Extract media from post JSON and create post_media records.

    Args:
        client: Supabase client
        post_id: The post's ID
        post_data: Full post JSON data

    Returns:
        List of created media_ids
    """
    from db_utils import generate_aws_id, PREFIX_MEDIA
    from media_cache import download_and_cache_media

    media_ids = []
    media = post_data.get('media', {})

    if not media:
        return media_ids

    # Handle single image
    if media.get('type') == 'image' and media.get('url'):
        media_info = download_and_cache_media(media['url'], 'image')
        media_id = generate_aws_id(PREFIX_MEDIA)

        client.table('post_media').insert({
            'media_id': media_id,
            'post_id': post_id,
            'media_type': 'image',
            'media_url': media['url'],
            'local_file_path': str(media_info['local_path']),
            'md5_sum': media_info['md5_sum'],
            'file_size': media_info['file_size'],
            'mime_type': media_info['mime_type'],
            'width': media_info.get('width'),
            'height': media_info.get('height'),
            'ai_analysis_status': 'not_started',
            'ai_analysis_log': json.dumps([{
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'event': 'media_downloaded',
                'status': 'success'
            }]),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).execute()

        media_ids.append(media_id)

    # Handle multiple images
    elif media.get('type') == 'images':
        for img in media.get('images', []):
            url = img.get('url')
            if not url:
                continue

            media_info = download_and_cache_media(url, 'image')
            media_id = generate_aws_id(PREFIX_MEDIA)

            # Similar insert as above...
            media_ids.append(media_id)

    # Handle video
    elif media.get('type') == 'video' and media.get('url'):
        # Similar handling for video...
        pass

    return media_ids
```

#### Update `import_directory()` to call media extraction

In `manage_data.py:176` (after creating post), add:

```python
# Extract and store media
try:
    media_ids = extract_and_store_media(client, post_id, post)
    if media_ids:
        print(f"  └─ Stored {len(media_ids)} media items")
except Exception as e:
    print(f"  └─ Error storing media: {e}")
    # Don't fail the entire import for media errors
```

### 5. AI Analysis Status Workflow

#### Status Transitions
```
not_started → started → completed
                  ↓
               failed
```

#### AI Analysis Log Structure (JSONB)
```json
[
  {
    "timestamp": "2025-12-01T10:30:00Z",
    "event": "media_downloaded",
    "status": "success",
    "details": {
      "file_size": 102400,
      "mime_type": "image/jpeg"
    }
  },
  {
    "timestamp": "2025-12-01T10:31:00Z",
    "event": "ai_analysis_started",
    "status": "success",
    "model": "gpt-4-vision-preview"
  },
  {
    "timestamp": "2025-12-01T10:31:15Z",
    "event": "ai_analysis_completed",
    "status": "success",
    "details": {
      "analysis_time_ms": 15000,
      "tokens_used": 850
    }
  }
]
```

## Implementation Plan

### Phase 1: Database Schema (✅ COMPLETED - December 1, 2025)
1. ✅ Created migration file `20251201123623_add_media_tracking_columns.sql`
2. ✅ Applied migration to database (version: 20251201203830)
3. ✅ `db_utils.py` already has `PREFIX_MEDIA = 'med'` (line 93)
4. ✅ Verified all schema changes (columns, indexes, constraints, comments)
5. ✅ Created verification script: `verify_media_schema.py`
6. ✅ Created completion summary: `specs/phase1_completion_summary.md`

**See `specs/phase1_completion_summary.md` for detailed completion report.**

### Phase 2: Local Storage (✅ COMPLETED - December 1, 2025)
1. ✅ Created `media_cache.py` module (500+ lines)
2. ✅ Implemented comprehensive cache management system
3. ✅ Created organized cache directory structure (`cache/media/{images,videos,documents}/`)
4. ✅ Implemented MD5 calculation and verification
5. ✅ Added parallel download support (ThreadPoolExecutor)
6. ✅ Installed Pillow dependency for image dimensions
7. ✅ Created comprehensive test suite (`test_media_cache.py`)
8. ✅ All offline tests passing (4/4)
9. ✅ CLI interface for testing and management

**See `specs/phase2_completion_summary.md` for detailed completion report.**

### Phase 3: Data Population (✅ COMPLETED - December 1, 2025)
1. ✅ Created `extract_and_store_media()` function in `manage_data.py` (120+ lines)
2. ✅ Integrated media extraction into `import_directory()` workflow
3. ✅ Media extracted for both new and existing posts
4. ✅ Enhanced statistics tracking (media_total, media_cached, media_errors)
5. ✅ Updated import summaries in both `manage_data.py` and `update_data.py`
6. ✅ Created `backfill_media.py` script (320+ lines)
7. ✅ Tested backfill with dry-run mode (found 27 media items in 5 posts)
8. ✅ Comprehensive error handling and logging

**See `specs/phase3_completion_summary.md` for detailed completion report.**

### Phase 4: S3 Archive (Medium Priority)
1. Create `media_archive.py` module
2. Implement S3 upload with retry logic
3. Add background job to archive cached media
4. Add CLI command: `python manage_media.py archive`

### Phase 5: AI Analysis Integration (Future)
1. Create `media_analysis.py` module
2. Implement OpenAI Vision API integration
3. Add queue-based processing for AI analysis
4. Add CLI command: `python manage_media.py analyze`

## New CLI Commands

### `manage_media.py` (new file)
```bash
# List all media for a post
python manage_media.py list --post-id p-abc123

# Download and cache media for all posts
python manage_media.py download-all

# Archive cached media to S3
python manage_media.py archive --all
python manage_media.py archive --post-id p-abc123

# Verify cached media integrity
python manage_media.py verify-cache

# Analyze media with AI
python manage_media.py analyze --status not_started
python manage_media.py analyze --media-id med-abc123

# Backfill media for existing posts
python manage_media.py backfill --start-date 2025-11-01
```

## Testing Strategy

### Unit Tests
- MD5 calculation accuracy
- Cache path generation
- Media type detection
- JSONB log manipulation

### Integration Tests
- Full media download and storage workflow
- Database insertion and querying
- S3 upload and verification
- Concurrent download handling

### Manual Testing
1. Import new posts with images → verify media_table populated
2. Download same image from different posts → verify deduplication by MD5
3. Check cache directory structure
4. Verify AI analysis status transitions

## Migration from Current System

### Backward Compatibility
- Keep existing `get_cached_image_path()` function in `interactive_posts.py`
- Gradually migrate to centralized `media_cache.py`
- Existing cache files remain valid (MD5-based naming already in place)

### Backfill Script
Create `backfill_media.py` to process existing posts:

```python
# Read all posts with media from database
# For each post:
#   - Check if post_media record exists
#   - If not, extract media from raw_json
#   - Download and cache media
#   - Create post_media record
```

## Performance Considerations

### Optimization Strategies
1. **Parallel Downloads**: Use asyncio/threading for concurrent media downloads
2. **Batch Inserts**: Insert multiple media records in single transaction
3. **Lazy S3 Archive**: Archive to S3 as background job, not blocking import
4. **Cache Warming**: Pre-download popular posts' media
5. **CDN Integration**: Consider CloudFront for S3 media delivery

### Resource Limits
- Max concurrent downloads: 5
- Download timeout: 30 seconds
- Max file size: 100MB (configurable)
- Cache size limit: 10GB (implement LRU eviction)

## Security Considerations

### Access Control
- S3 bucket: Private with signed URLs for access
- Local cache: Readable only by application user
- Media URLs: Validate before download (no SSRF)

### Data Privacy
- No PII in media filenames
- Audit log for media access
- Retention policy for cached files

## Monitoring and Metrics

### Key Metrics to Track
- Media download success rate
- Cache hit rate
- Average download time
- Storage usage (local + S3)
- AI analysis queue depth
- Failed downloads by error type

### Logging
- All media operations logged to `log/media.log`
- Structured logging with correlation IDs
- Error tracking with Sentry integration

## Future Enhancements

### Potential Additions
1. **Thumbnail Generation**: Auto-generate thumbnails for images
2. **Video Transcoding**: Convert videos to web-friendly formats
3. **OCR Integration**: Extract text from images
4. **Duplicate Detection**: Perceptual hashing for similar images
5. **Media CDN**: Serve cached media via local HTTP server
6. **Batch Analysis**: Analyze multiple media items in one API call
7. **Cost Tracking**: Track S3 and AI API costs per post/profile

## References

### Related Files
- `supabase/migrations/20251130223349_create_schema.sql:186-210` - Current post_media table
- `interactive_posts.py:47-136` - Existing image cache implementation
- `manage_data.py:85-204` - Post import logic
- `update_data.py` - Main data update workflow

### External Documentation
- [Supabase Storage](https://supabase.com/docs/guides/storage)
- [AWS S3 Python SDK](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3.html)
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision)
