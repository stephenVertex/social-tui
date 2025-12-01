# Media Import Quick Start Guide

## Overview

Media extraction is now fully integrated into the data import workflow. All media files (images, videos) from LinkedIn posts are automatically downloaded, cached, and stored in the database during import.

## Automatic Media Extraction

### Regular Import

Media is extracted automatically during normal import operations:

```bash
# Standard update (includes media extraction)
python update_data.py

# Manual import (includes media extraction)
python manage_data.py import data/20251201_120000/linkedin
```

**What happens automatically**:
1. Posts are imported as usual
2. Media URLs are extracted from post JSON
3. Media files are downloaded and cached
4. MD5 checksums are calculated
5. Image dimensions are extracted
6. Database records are created in `post_media` table
7. AI analysis log is initialized

### Import Summary

The import summary now includes media statistics:

```
Import Summary:
  Run ID:     run-abc12345
  Processed:  100
  New:        50
  Duplicates: 50
  Errors:     0

  Media:
    Found:    120
    Cached:   115
    Errors:   5
```

## Backfill Historical Posts

For posts that were imported before media extraction was added:

### Preview (Dry Run)

```bash
# See what would be processed
python backfill_media.py --dry-run

# Preview first 10 posts
python backfill_media.py --dry-run --limit 10
```

Output:
```
======================================================================
DRY RUN - No changes will be made
======================================================================

Would process 5 posts:
  1. p-bc034097 - images (6 item(s))
  2. p-2dfb16bc - image (1 item(s))
  3. p-d31f0cb5 - images (18 item(s))
  4. p-7dee82a5 - image (1 item(s))
  5. p-61470af0 - video (1 item(s))
```

### Process Posts

```bash
# Process first 10 posts
python backfill_media.py --limit 10

# Process recent posts (since November 1)
python backfill_media.py --start-date 2025-11-01

# Process all posts in small batches
python backfill_media.py --batch-size 5

# Full backfill (all posts)
python backfill_media.py
```

### Progress Tracking

During backfill, you'll see progress for each batch:

```
Batch 1/5 (10 posts)
----------------------------------------------------------------------
  ✓ p-abc123: Cached 6/6 media
  ✓ p-def456: Cached 1/1 media
  ✓ p-ghi789: Cached 18/18 media
  ...
```

## Monitoring

### Cache Statistics

```bash
python media_cache.py stats
```

Output:
```
Media Cache Statistics:
==================================================
Total Files: 127
Total Size:  45.2 MB

By Type:
  Image: 125 files, 44.8 MB
  Video: 2 files, 0.4 MB
  Document: 0 files, 0.0 B
```

### Database Counts

```bash
# Count media records
python -c "from supabase_client import get_supabase_client; \
  c = get_supabase_client(); \
  r = c.table('post_media').select('media_id', count='exact').execute(); \
  print(f'Total media records: {r.count}')"
```

## Common Scenarios

### Scenario 1: Fresh Import

You run a fresh import with new posts:

```bash
python update_data.py
```

**Result**:
- Posts imported
- Media automatically extracted and cached
- Ready to view in `interactive_posts.py`

### Scenario 2: Re-Import Existing Posts

You re-run import on data that's already in the database:

```bash
python update_data.py --retry
```

**Result**:
- Posts marked as duplicates
- Media still extracted (if not already present)
- No duplicate media downloads

### Scenario 3: Backfill Old Posts

You want to add media for posts imported before this feature:

```bash
# Preview first
python backfill_media.py --dry-run --limit 20

# Process them
python backfill_media.py --limit 20

# With rate limit protection (recommended for large batches)
python backfill_media.py --limit 100 --sleep-min 1 --sleep-max 3
```

**Result**:
- Historical posts now have media records
- Media files cached locally
- Can view images in interactive viewer

## File Locations

### Cached Media

```
cache/media/
├── images/       # Image files (.jpg, .png, .gif, .webp)
│   └── a1b2c3d4e5f6.jpg
├── videos/       # Video files (.mp4, .webm, .mov)
│   └── x9y8z7w6v5u4.mp4
└── documents/    # Document files (.pdf)
```

Files are named by MD5 checksum for deduplication.

### Database Records

**post_media table**:
- `media_id`: Unique ID (med-abc12345)
- `post_id`: Associated post
- `media_url`: Original URL
- `local_file_path`: Path to cached file
- `md5_sum`: MD5 checksum
- `file_size`: Size in bytes
- `mime_type`: File MIME type
- `width`, `height`: Image dimensions
- `ai_analysis_status`: 'not_started', 'started', 'completed', 'failed'
- `ai_analysis_log`: JSONB array of events

## Error Handling

### Media Download Failures

**What happens**:
- Error is logged
- Post import continues
- Media error count incremented
- Other media in the post still processed

**How to retry**:
```bash
# Re-run backfill for failed items
python backfill_media.py --limit 10
```

### Network Timeouts

**Default timeout**: 30 seconds per file

**If you experience timeouts**:
- Check network connection
- LinkedIn URLs may be rate-limited
- Retry later with backfill script

### Disk Space

**Monitor cache size**:
```bash
du -sh cache/media/
```

**If running low on space**:
- Consider S3 archiving (Phase 4)
- Implement cache cleanup strategy
- Use smaller batch sizes during backfill

## Tips

### 1. Start Small

When backfilling, start with a small batch to verify everything works:

```bash
python backfill_media.py --dry-run --limit 5
python backfill_media.py --limit 5
```

### 2. Use Date Filters

Process only recent posts to save time:

```bash
python backfill_media.py --start-date 2025-11-01
```

### 3. Batch Processing

For large backlogs, use small batches to avoid memory issues:

```bash
python backfill_media.py --batch-size 5
```

### 4. Monitor Progress

Check cache stats before and after:

```bash
python media_cache.py stats
```

### 5. Dry Run First

Always preview with `--dry-run` for large operations:

```bash
python backfill_media.py --dry-run
```

### 6. Rate Limit Protection

For large backfills (100+ posts), use sleep parameters to avoid rate limiting:

```bash
# Conservative (recommended for 500+ posts)
python backfill_media.py --sleep-min 1 --sleep-max 3 --batch-size 20

# Balanced (good for 100-500 posts)
python backfill_media.py --sleep-min 0.5 --sleep-max 2 --batch-size 50

# Fast (for small batches < 100 posts)
python backfill_media.py --sleep-min 0.5 --sleep-max 1.5
```

**Sleep parameters:**
- `--sleep-min`: Minimum seconds to wait between posts (default: 0.5)
- `--sleep-max`: Maximum seconds to wait between posts (default: 2.0)
- Random sleep time chosen between min and max for each post
- No sleep after the last post in a batch

## Troubleshooting

### "No posts need media extraction"

**Possible causes**:
1. All posts already have media records
2. No posts have media in their JSON
3. Date filter excludes all posts

**Solution**:
```bash
# Check without filters
python backfill_media.py --dry-run
```

### High Error Rate

**Possible causes**:
1. Network connectivity issues
2. LinkedIn URL changes
3. Rate limiting

**Solution**:
- Retry later
- Use smaller batches
- Check network connection

### Memory Issues

**Symptoms**:
- Slow performance
- System becoming unresponsive

**Solution**:
```bash
# Use smaller batches
python backfill_media.py --batch-size 3
```

## Next Steps

After importing media:

1. **View in Interactive Viewer**:
   ```bash
   python interactive_posts.py --kitty-images
   ```

2. **Check Statistics**:
   ```bash
   python media_cache.py stats
   ```

3. **Future: AI Analysis** (Phase 5):
   - Automatic image analysis
   - Content extraction
   - Tag suggestions

## Files Reference

- **Import**: `manage_data.py`, `update_data.py`
- **Backfill**: `backfill_media.py`
- **Cache**: `media_cache.py`
- **Viewer**: `interactive_posts.py`

## Documentation

- **Phase 3 Details**: `specs/phase3_completion_summary.md`
- **Cache Guide**: `MEDIA_CACHE_QUICKSTART.md`
- **Full Spec**: `specs/media_handling.md`
