#!/usr/bin/env python3
"""
Media cache management module for social-tui.

Handles downloading, caching, and verification of media files (images, videos, documents)
with MD5-based deduplication and integrity checking.
"""

import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Cache directory structure
CACHE_ROOT = Path("cache/media")
CACHE_DIRS = {
    'image': CACHE_ROOT / "images",
    'video': CACHE_ROOT / "videos",
    'document': CACHE_ROOT / "documents",
}

# Ensure cache directories exist
for cache_dir in CACHE_DIRS.values():
    cache_dir.mkdir(parents=True, exist_ok=True)

# Media type mappings
MIME_TO_MEDIA_TYPE = {
    'image/jpeg': 'image',
    'image/jpg': 'image',
    'image/png': 'image',
    'image/gif': 'image',
    'image/webp': 'image',
    'video/mp4': 'video',
    'video/webm': 'video',
    'video/quicktime': 'video',
    'application/pdf': 'document',
}

# Extension to media type mapping (fallback)
EXT_TO_MEDIA_TYPE = {
    '.jpg': 'image',
    '.jpeg': 'image',
    '.png': 'image',
    '.gif': 'image',
    '.webp': 'image',
    '.mp4': 'video',
    '.webm': 'video',
    '.mov': 'video',
    '.pdf': 'document',
}

# Default User-Agent for downloads
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


def calculate_md5(file_path: Path, chunk_size: int = 8192) -> str:
    """
    Calculate MD5 checksum of a file.

    Args:
        file_path: Path to the file
        chunk_size: Size of chunks to read (default 8KB)

    Returns:
        MD5 checksum as hex string

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    md5_hash = hashlib.md5()

    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except IOError as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise


def calculate_md5_from_bytes(data: bytes) -> str:
    """
    Calculate MD5 checksum from bytes.

    Args:
        data: Bytes to hash

    Returns:
        MD5 checksum as hex string
    """
    return hashlib.md5(data).hexdigest()


def get_extension_from_url(url: str) -> str:
    """
    Extract file extension from URL.

    Args:
        url: Media URL

    Returns:
        File extension with leading dot (e.g., '.jpg'), or '.bin' if unknown
    """
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Try to get extension from path
    for ext in EXT_TO_MEDIA_TYPE.keys():
        if ext in path:
            return ext

    return '.bin'


def detect_media_type(url: str, mime_type: Optional[str] = None) -> str:
    """
    Detect media type from URL or MIME type.

    Args:
        url: Media URL
        mime_type: Optional MIME type

    Returns:
        Media type: 'image', 'video', or 'document'
    """
    # Try MIME type first
    if mime_type and mime_type in MIME_TO_MEDIA_TYPE:
        return MIME_TO_MEDIA_TYPE[mime_type]

    # Fall back to extension
    ext = get_extension_from_url(url)
    if ext in EXT_TO_MEDIA_TYPE:
        return EXT_TO_MEDIA_TYPE[ext]

    # Default to image (most common case)
    return 'image'


def get_media_cache_path(media_type: str, md5_sum: str, extension: str) -> Path:
    """
    Get the local cache path for a media file.

    Args:
        media_type: Type of media ('image', 'video', 'document')
        md5_sum: MD5 checksum of the file
        extension: File extension (with leading dot)

    Returns:
        Path to the cached file
    """
    cache_dir = CACHE_DIRS.get(media_type, CACHE_DIRS['image'])
    return cache_dir / f"{md5_sum}{extension}"


def verify_cached_media(local_path: Path, expected_md5: str) -> bool:
    """
    Verify integrity of cached media file.

    Args:
        local_path: Path to cached file
        expected_md5: Expected MD5 checksum

    Returns:
        True if file exists and MD5 matches, False otherwise
    """
    if not local_path.exists():
        return False

    try:
        actual_md5 = calculate_md5(local_path)
        return actual_md5 == expected_md5
    except Exception as e:
        logger.error(f"Error verifying cached media {local_path}: {e}")
        return False


def download_media(media_url: str, timeout: int = 30) -> Tuple[bytes, Optional[str]]:
    """
    Download media from URL with proper headers.

    Args:
        media_url: URL of the media
        timeout: Download timeout in seconds

    Returns:
        Tuple of (media data as bytes, MIME type)

    Raises:
        urllib.error.URLError: If download fails
        urllib.error.HTTPError: If HTTP error occurs
    """
    req = Request(
        media_url,
        headers={'User-Agent': DEFAULT_USER_AGENT}
    )

    with urlopen(req, timeout=timeout) as response:
        data = response.read()
        mime_type = response.headers.get('Content-Type', '').split(';')[0].strip()
        return data, mime_type if mime_type else None


def get_image_dimensions(file_path: Path) -> Optional[Tuple[int, int]]:
    """
    Get image dimensions (width, height) if available.

    Args:
        file_path: Path to image file

    Returns:
        Tuple of (width, height) or None if not an image or error
    """
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size
    except ImportError:
        logger.warning("PIL not installed, cannot get image dimensions")
        return None
    except Exception as e:
        logger.debug(f"Could not get dimensions for {file_path}: {e}")
        return None


def download_and_cache_media(
    media_url: str,
    media_type: Optional[str] = None,
    timeout: int = 30
) -> Dict:
    """
    Download media from URL, calculate MD5, and cache locally.

    This function:
    1. Downloads the media file
    2. Calculates MD5 checksum
    3. Determines media type and extension
    4. Caches the file with MD5-based naming
    5. Extracts metadata (size, dimensions, etc.)

    Args:
        media_url: URL of the media to download
        media_type: Optional media type override ('image', 'video', 'document')
        timeout: Download timeout in seconds

    Returns:
        Dictionary with:
            - md5_sum: MD5 checksum of the file
            - local_path: Path to cached file
            - file_size: Size in bytes
            - mime_type: MIME type of the file
            - media_type: Type of media
            - width: Image width (if applicable)
            - height: Image height (if applicable)
            - extension: File extension
            - url: Original URL

    Raises:
        Exception: If download or caching fails
    """
    logger.info(f"Downloading media: {media_url}")

    try:
        # Download the media
        data, mime_type = download_media(media_url, timeout=timeout)

        # Calculate MD5 from downloaded data
        md5_sum = calculate_md5_from_bytes(data)

        # Detect media type
        if not media_type:
            media_type = detect_media_type(media_url, mime_type)

        # Get extension
        extension = get_extension_from_url(media_url)

        # Get cache path
        cache_path = get_media_cache_path(media_type, md5_sum, extension)

        # Check if already cached
        if cache_path.exists():
            logger.info(f"Media already cached: {cache_path.name}")
            # Verify integrity
            if not verify_cached_media(cache_path, md5_sum):
                logger.warning(f"Cached file corrupted, re-downloading: {cache_path}")
                cache_path.unlink()
            else:
                # File exists and is valid, just return metadata
                file_size = cache_path.stat().st_size
                dimensions = get_image_dimensions(cache_path) if media_type == 'image' else None

                return {
                    'md5_sum': md5_sum,
                    'local_path': cache_path,
                    'file_size': file_size,
                    'mime_type': mime_type,
                    'media_type': media_type,
                    'width': dimensions[0] if dimensions else None,
                    'height': dimensions[1] if dimensions else None,
                    'extension': extension,
                    'url': media_url
                }

        # Save to cache
        logger.info(f"Caching to: {cache_path}")
        with open(cache_path, 'wb') as f:
            f.write(data)

        # Get file size
        file_size = len(data)

        # Get dimensions if it's an image
        dimensions = get_image_dimensions(cache_path) if media_type == 'image' else None

        result = {
            'md5_sum': md5_sum,
            'local_path': cache_path,
            'file_size': file_size,
            'mime_type': mime_type,
            'media_type': media_type,
            'width': dimensions[0] if dimensions else None,
            'height': dimensions[1] if dimensions else None,
            'extension': extension,
            'url': media_url
        }

        logger.info(f"Successfully cached: {cache_path.name} ({file_size:,} bytes)")
        return result

    except Exception as e:
        logger.error(f"Error downloading/caching media {media_url}: {e}")
        raise


def download_multiple_media(
    media_urls: List[str],
    max_workers: int = 5,
    timeout: int = 30
) -> List[Dict]:
    """
    Download multiple media files in parallel.

    Args:
        media_urls: List of media URLs to download
        max_workers: Maximum number of concurrent downloads
        timeout: Download timeout per file in seconds

    Returns:
        List of result dictionaries (same as download_and_cache_media)
        Failed downloads are logged but not included in results
    """
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_url = {
            executor.submit(download_and_cache_media, url, timeout=timeout): url
            for url in media_urls
        }

        # Collect results as they complete
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"✓ Downloaded: {url}")
            except Exception as e:
                logger.error(f"✗ Failed to download {url}: {e}")

    return results


def find_cached_by_md5(md5_sum: str) -> Optional[Path]:
    """
    Find a cached file by its MD5 checksum.

    Args:
        md5_sum: MD5 checksum to search for

    Returns:
        Path to the cached file, or None if not found
    """
    for cache_dir in CACHE_DIRS.values():
        for file_path in cache_dir.glob(f"{md5_sum}.*"):
            return file_path
    return None


def find_cached_by_url(url: str) -> Optional[Path]:
    """
    Find a cached file by its original URL (legacy support).

    This uses the old URL-based MD5 hash method for backward compatibility
    with existing cache files.

    Args:
        url: Original URL of the media

    Returns:
        Path to the cached file, or None if not found
    """
    # Calculate MD5 of the URL (legacy method)
    url_md5 = hashlib.md5(url.encode('utf-8')).hexdigest()

    # Search in all cache directories
    for cache_dir in CACHE_DIRS.values():
        for file_path in cache_dir.glob(f"{url_md5}.*"):
            return file_path

    return None


def get_cache_stats() -> Dict:
    """
    Get statistics about the media cache.

    Returns:
        Dictionary with cache statistics:
            - total_files: Total number of cached files
            - total_size: Total size in bytes
            - by_type: Dict of counts and sizes by media type
    """
    stats = {
        'total_files': 0,
        'total_size': 0,
        'by_type': {}
    }

    for media_type, cache_dir in CACHE_DIRS.items():
        files = list(cache_dir.glob("*"))
        # Filter out .gitkeep
        files = [f for f in files if f.name != '.gitkeep']

        count = len(files)
        size = sum(f.stat().st_size for f in files)

        stats['by_type'][media_type] = {
            'count': count,
            'size': size
        }
        stats['total_files'] += count
        stats['total_size'] += size

    return stats


def format_size(size_bytes: int) -> str:
    """
    Format byte size as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python media_cache.py <url>        - Download and cache a single URL")
        print("  python media_cache.py stats        - Show cache statistics")
        print("  python media_cache.py verify <md5> - Verify a cached file")
        sys.exit(1)

    command = sys.argv[1]

    if command == "stats":
        stats = get_cache_stats()
        print("\nMedia Cache Statistics:")
        print("=" * 50)
        print(f"Total Files: {stats['total_files']}")
        print(f"Total Size:  {format_size(stats['total_size'])}")
        print("\nBy Type:")
        for media_type, type_stats in stats['by_type'].items():
            print(f"  {media_type.capitalize()}: {type_stats['count']} files, {format_size(type_stats['size'])}")

    elif command == "verify" and len(sys.argv) == 3:
        md5_sum = sys.argv[2]
        cached_file = find_cached_by_md5(md5_sum)
        if cached_file:
            is_valid = verify_cached_media(cached_file, md5_sum)
            print(f"File: {cached_file}")
            print(f"Valid: {is_valid}")
        else:
            print(f"No cached file found with MD5: {md5_sum}")

    else:
        # Assume it's a URL to download
        url = sys.argv[1]
        print(f"Downloading: {url}")
        result = download_and_cache_media(url)
        print("\nResult:")
        for key, value in result.items():
            print(f"  {key}: {value}")
