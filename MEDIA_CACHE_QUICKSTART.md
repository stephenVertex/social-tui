# Media Cache Quick Start Guide

## Overview

The `media_cache.py` module provides a comprehensive system for downloading, caching, and managing media files (images, videos, documents) with MD5-based deduplication and integrity checking.

## Quick Examples

### Download a Single Image

```python
from media_cache import download_and_cache_media

result = download_and_cache_media("https://example.com/photo.jpg")

print(f"Cached at: {result['local_path']}")
print(f"MD5: {result['md5_sum']}")
print(f"Size: {result['file_size']} bytes")
```

### Download Multiple Images in Parallel

```python
from media_cache import download_multiple_media

urls = [
    "https://example.com/image1.jpg",
    "https://example.com/image2.jpg",
    "https://example.com/image3.jpg",
]

# Download with 5 concurrent workers
results = download_multiple_media(urls, max_workers=5)

print(f"Downloaded {len(results)} files")
```

### Check Cache Statistics

```python
from media_cache import get_cache_stats, format_size

stats = get_cache_stats()

print(f"Total: {stats['total_files']} files")
print(f"Size: {format_size(stats['total_size'])}")

for media_type, type_stats in stats['by_type'].items():
    print(f"  {media_type}: {type_stats['count']} files")
```

### Verify a Cached File

```python
from media_cache import verify_cached_media, find_cached_by_md5

md5 = "a1b2c3d4e5f6"
cached_file = find_cached_by_md5(md5)

if cached_file:
    is_valid = verify_cached_media(cached_file, md5)
    print(f"Valid: {is_valid}")
```

## CLI Usage

```bash
# Show cache statistics
python media_cache.py stats

# Download a file
python media_cache.py https://example.com/image.jpg

# Verify a cached file
python media_cache.py verify a1b2c3d4e5f6
```

## Testing

```bash
# Run all tests (offline only)
python test_media_cache.py

# Run specific tests
python test_media_cache.py stats
python test_media_cache.py download
python test_media_cache.py parallel
```

## Key Features

- **Content-based deduplication**: Same content = same cache file
- **Parallel downloads**: Up to 5 concurrent downloads
- **Integrity verification**: MD5 checksums on all operations
- **Multiple media types**: Images, videos, documents
- **Automatic retry**: Re-downloads corrupted files
- **Image dimensions**: Automatic width/height extraction

## Directory Structure

```
cache/media/
├── images/         # Image files (.jpg, .png, .gif, .webp)
├── videos/         # Video files (.mp4, .webm, .mov)
└── documents/      # Document files (.pdf)
```

Files are named: `{md5_sum}.{extension}`

## Return Value Structure

```python
{
    'md5_sum': 'a1b2c3d4e5f6...',      # MD5 checksum
    'local_path': Path(...),            # Path to cached file
    'file_size': 102400,                # Size in bytes
    'mime_type': 'image/jpeg',          # MIME type
    'media_type': 'image',              # Type: image/video/document
    'width': 1920,                      # Image width (if applicable)
    'height': 1080,                     # Image height (if applicable)
    'extension': '.jpg',                # File extension
    'url': 'https://...'                # Original URL
}
```

## Performance

- **Chunked reading**: 8KB chunks (memory efficient)
- **Parallel downloads**: 5 concurrent workers (default)
- **Timeout**: 30 seconds per file (configurable)
- **Deduplication**: Single copy per unique file

## Error Handling

```python
try:
    result = download_and_cache_media(url)
except Exception as e:
    print(f"Download failed: {e}")
```

Errors are logged but don't crash the application.

## Integration Example

```python
from media_cache import download_and_cache_media
from supabase_client import get_supabase_client
from db_utils import generate_aws_id, PREFIX_MEDIA

def store_media(post_id, media_url):
    # Download and cache
    result = download_and_cache_media(media_url)

    # Store in database
    client = get_supabase_client()
    client.table('post_media').insert({
        'media_id': generate_aws_id(PREFIX_MEDIA),
        'post_id': post_id,
        'media_type': result['media_type'],
        'media_url': result['url'],
        'local_file_path': str(result['local_path']),
        'md5_sum': result['md5_sum'],
        'file_size': result['file_size'],
        'mime_type': result['mime_type'],
        'width': result.get('width'),
        'height': result.get('height'),
    }).execute()
```

## Dependencies

- Python 3.13+
- `pillow` (for image dimensions)

Install with:
```bash
uv pip install pillow
```

## Logging

The module uses Python's logging framework:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Use the module
from media_cache import download_and_cache_media
result = download_and_cache_media(url)
```

## Files

- **`media_cache.py`**: Main module (500+ lines)
- **`test_media_cache.py`**: Test suite (300+ lines)
- **`specs/phase2_completion_summary.md`**: Detailed documentation

## Next Steps

See `specs/media_handling.md` for the complete specification and upcoming phases.
