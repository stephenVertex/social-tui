#!/usr/bin/env python3
"""
Backfill media for existing posts in the database.

This script:
1. Finds all posts that have media in their raw_json
2. Checks if media records already exist
3. Downloads and caches missing media
4. Creates post_media records

Usage:
    python backfill_media.py                    # Process all posts
    python backfill_media.py --limit 10         # Process first 10 posts
    python backfill_media.py --start-date 2025-11-01  # Posts since date
    python backfill_media.py --dry-run          # Show what would be done
    python backfill_media.py --sleep-min 1 --sleep-max 3  # Custom sleep to avoid rate limits
"""

import argparse
import json
import logging
import time
import random
from datetime import datetime, timezone
from typing import List, Dict

from supabase_client import get_supabase_client
from manage_data import extract_and_store_media

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_posts_needing_media(client, limit: int = None, start_date: str = None) -> List[Dict]:
    """
    Get posts that have media in raw_json but no media records.

    Args:
        client: Supabase client
        limit: Optional limit on number of posts to return
        start_date: Optional start date filter (YYYY-MM-DD)

    Returns:
        List of post dictionaries
    """
    logger.info("Querying posts that need media extraction...")

    # Build query
    query = client.table('posts').select('post_id, raw_json, first_seen_at')

    # Add date filter if specified
    if start_date:
        query = query.gte('first_seen_at', f"{start_date}T00:00:00Z")

    # Order by newest first
    query = query.order('first_seen_at', desc=True)

    # Add limit if specified
    if limit:
        query = query.limit(limit)

    result = query.execute()
    posts = result.data

    logger.info(f"Found {len(posts)} posts to check")

    # Filter to posts that have media in raw_json
    posts_with_media = []
    for post in posts:
        try:
            raw_data = json.loads(post['raw_json'])
            media = raw_data.get('media', {})

            if media and media.get('type'):
                # Check if media records already exist
                existing = client.table('post_media').select('media_id').eq(
                    'post_id', post['post_id']
                ).execute()

                if not existing.data:
                    posts_with_media.append({
                        'post_id': post['post_id'],
                        'raw_data': raw_data,
                        'first_seen_at': post.get('first_seen_at')
                    })
        except Exception as e:
            logger.error(f"Error checking post {post['post_id']}: {e}")
            continue

    logger.info(f"Found {len(posts_with_media)} posts needing media extraction")
    return posts_with_media


def backfill_media(
    dry_run: bool = False,
    limit: int = None,
    start_date: str = None,
    batch_size: int = 10,
    sleep_min: float = 0.5,
    sleep_max: float = 2.0
) -> Dict:
    """
    Backfill media for existing posts.

    Args:
        dry_run: If True, only show what would be done
        limit: Optional limit on number of posts to process
        start_date: Optional start date filter (YYYY-MM-DD)
        batch_size: Number of posts to process in each batch
        sleep_min: Minimum sleep time between posts (seconds)
        sleep_max: Maximum sleep time between posts (seconds)

    Returns:
        Dictionary with backfill statistics
    """
    client = get_supabase_client()

    stats = {
        'posts_checked': 0,
        'posts_with_media': 0,
        'media_total': 0,
        'media_cached': 0,
        'media_errors': 0,
        'posts_processed': 0,
        'posts_failed': 0
    }

    # Get posts needing media extraction
    posts = get_posts_needing_media(client, limit=limit, start_date=start_date)
    stats['posts_checked'] = limit or len(posts)
    stats['posts_with_media'] = len(posts)

    if not posts:
        logger.info("No posts need media extraction")
        return stats

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN - No changes will be made")
        print("=" * 70)
        print(f"\nWould process {len(posts)} posts:")
        for i, post in enumerate(posts[:10], 1):
            raw_data = post['raw_data']
            media = raw_data.get('media', {})
            media_type = media.get('type', 'unknown')

            # Count media items
            if media_type == 'images':
                count = len(media.get('images', []))
            elif media_type in ['image', 'video']:
                count = 1
            else:
                count = 0

            print(f"  {i}. {post['post_id']} - {media_type} ({count} item(s))")

        if len(posts) > 10:
            print(f"  ... and {len(posts) - 10} more")

        return stats

    # Process posts in batches
    print("\n" + "=" * 70)
    print("Backfilling Media")
    print("=" * 70)
    print(f"Processing {len(posts)} posts in batches of {batch_size}...")
    print()

    for i in range(0, len(posts), batch_size):
        batch = posts[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} posts)")
        print("-" * 70)

        for post in batch:
            post_id = post['post_id']
            raw_data = post['raw_data']

            try:
                # Extract and store media
                media_stats = extract_and_store_media(client, post_id, raw_data)

                stats['posts_processed'] += 1
                stats['media_total'] += media_stats['media_count']
                stats['media_cached'] += media_stats['media_cached']
                stats['media_errors'] += media_stats['media_errors']

                if media_stats['media_cached'] > 0:
                    print(f"  ✓ {post_id}: Cached {media_stats['media_cached']}/{media_stats['media_count']} media")
                elif media_stats['media_count'] > 0:
                    print(f"  ✗ {post_id}: Failed to cache media")
                else:
                    print(f"  - {post_id}: No media found")

            except Exception as e:
                logger.error(f"Error processing post {post_id}: {e}")
                stats['posts_failed'] += 1
                print(f"  ✗ {post_id}: Error - {e}")

            # Sleep between posts to avoid rate limiting
            if sleep_min > 0 and post != batch[-1]:  # Don't sleep after last post in batch
                sleep_time = random.uniform(sleep_min, sleep_max)
                time.sleep(sleep_time)

    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill media for existing posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backfill_media.py                          # Process all posts
  python backfill_media.py --limit 10               # Process first 10 posts
  python backfill_media.py --start-date 2025-11-01  # Posts since date
  python backfill_media.py --dry-run                # Show what would be done
  python backfill_media.py --batch-size 5           # Process 5 posts at a time
  python backfill_media.py --sleep-min 1 --sleep-max 3  # Custom sleep range
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of posts to process'
    )
    parser.add_argument(
        '--start-date',
        help='Only process posts since this date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of posts to process in each batch (default: 10)'
    )
    parser.add_argument(
        '--sleep-min',
        type=float,
        default=0.5,
        help='Minimum sleep time between posts in seconds (default: 0.5)'
    )
    parser.add_argument(
        '--sleep-max',
        type=float,
        default=2.0,
        help='Maximum sleep time between posts in seconds (default: 2.0)'
    )

    args = parser.parse_args()

    try:
        stats = backfill_media(
            dry_run=args.dry_run,
            limit=args.limit,
            start_date=args.start_date,
            batch_size=args.batch_size,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max
        )

        # Print summary
        print("\n" + "=" * 70)
        print("Backfill Summary")
        print("=" * 70)
        print(f"Posts Checked:     {stats['posts_checked']}")
        print(f"Posts with Media:  {stats['posts_with_media']}")
        print(f"Posts Processed:   {stats['posts_processed']}")
        print(f"Posts Failed:      {stats['posts_failed']}")
        print(f"\nMedia:")
        print(f"  Found:           {stats['media_total']}")
        print(f"  Cached:          {stats['media_cached']}")
        print(f"  Errors:          {stats['media_errors']}")
        print("=" * 70)

        if not args.dry_run:
            print("✓ Backfill completed")
        else:
            print("ℹ Dry run completed (no changes made)")

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
