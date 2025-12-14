#!/usr/bin/env python3
"""
Update statistics for existing YouTube videos.

This script:
1. Queries existing YouTube videos from the database
2. Fetches current statistics from YouTube API
3. Inserts new data_downloads records for time-series tracking
4. Updates last_synced_at for YouTube profiles
5. Shows updated statistics

Usage:
    uv run python update_youtube_stats.py                    # Update videos from last 30 days
    uv run python update_youtube_stats.py --days-back 7      # Update videos from last 7 days
    uv run python update_youtube_stats.py --limit 100        # Update only 100 most recent videos
    uv run python update_youtube_stats.py --all              # Update all YouTube videos
    uv run python update_youtube_stats.py --channel USERNAME # Update specific channel only
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase_client import get_supabase_client
from manage_data import create_download_run, complete_download_run

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


def get_youtube_service():
    """Builds and returns the YouTube API service."""
    try:
        return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=YOUTUBE_API_KEY)
    except Exception as e:
        print(f"Error building YouTube service: {e}")
        return None


def get_existing_youtube_videos(client, days_back=None, limit=None, channel_username=None):
    """Retrieves existing YouTube videos from the database.

    Args:
        client: Supabase client
        days_back: Only get videos from last N days (None = all videos)
        limit: Maximum number of videos to retrieve
        channel_username: Filter by specific channel username

    Returns:
        List of video records
    """
    try:
        query = client.table('posts').select('post_id, urn, author_username, posted_at_timestamp, url')

        # Filter by platform
        query = query.eq('platform', 'youtube')

        # Filter by channel if specified
        if channel_username:
            query = query.eq('author_username', channel_username)

        # Filter by date if specified
        if days_back:
            cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000)
            query = query.gte('posted_at_timestamp', cutoff_timestamp)

        # Order by most recent first
        query = query.order('posted_at_timestamp', desc=True)

        # Apply limit if specified
        if limit:
            query = query.limit(limit)

        response = query.execute()
        return response.data
    except Exception as e:
        print(f"Error fetching existing YouTube videos: {e}")
        return []


def batch_fetch_video_stats(youtube, video_ids: List[str]) -> Dict[str, Any]:
    """Fetches statistics for a batch of video IDs.

    Args:
        youtube: YouTube API service
        video_ids: List of YouTube video IDs (max 50)

    Returns:
        Dictionary mapping video_id to stats
    """
    if not video_ids:
        return {}

    # YouTube API allows up to 50 IDs per request
    batch_size = 50
    all_stats = {}

    for i in range(0, len(video_ids), batch_size):
        batch = video_ids[i:i + batch_size]

        try:
            response = youtube.videos().list(
                id=",".join(batch),
                part="statistics"
            ).execute()

            for item in response.get("items", []):
                video_id = item["id"]
                stats = item.get("statistics", {})
                all_stats[video_id] = {
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                }
        except HttpError as e:
            print(f"  - HTTP error fetching stats for batch: {e.resp.status} - {e.content}")
        except Exception as e:
            print(f"  - Error fetching stats for batch: {e}")

    return all_stats


def insert_stats_snapshot(client, post_id: str, video_id: str, stats: Dict[str, int]) -> bool:
    """Inserts a new data_downloads record for a video.

    Args:
        client: Supabase client
        post_id: Internal post ID
        video_id: YouTube video ID
        stats: Dictionary with views, likes, comments

    Returns:
        True if successful, False otherwise
    """
    try:
        download_id = f"d-{uuid.uuid4().hex[:8]}"
        data_download_record = {
            'download_id': download_id,
            'post_id': post_id,
            'downloaded_at': datetime.now(timezone.utc).isoformat(),
            'total_reactions': stats.get('likes', 0),
            'stats_json': json.dumps(stats)
        }

        client.table('data_downloads').insert(data_download_record).execute()
        return True
    except Exception as e:
        print(f"  - Error inserting stats for video {video_id}: {e}")
        return False


def update_profile_sync_time(client, channel_usernames: List[str]) -> int:
    """Updates last_synced_at for YouTube profiles.

    Args:
        client: Supabase client
        channel_usernames: List of channel usernames to update

    Returns:
        Number of profiles updated
    """
    if not channel_usernames:
        return 0

    try:
        sync_time = datetime.now(timezone.utc).isoformat()
        updated_count = 0

        for username in channel_usernames:
            try:
                result = client.table('profiles').update({
                    'last_synced_at': sync_time,
                    'updated_at': sync_time
                }).eq('username', username).eq('platform', 'youtube').execute()

                if result.data:
                    updated_count += 1
            except Exception as e:
                print(f"  - Warning: Could not update sync time for {username}: {e}")

        print(f"  - Updated last_synced_at for {updated_count} channel(s)")
        return updated_count

    except Exception as e:
        print(f"  - Error updating profile sync times: {e}")
        return 0


def update_video_stats(client, youtube, videos: List[Dict[str, Any]], run_id: str) -> Dict[str, int]:
    """Updates statistics for a list of videos.

    Args:
        client: Supabase client
        youtube: YouTube API service
        videos: List of video records from database
        run_id: Download run ID

    Returns:
        Dictionary with update statistics
    """
    stats = {
        'total': len(videos),
        'updated': 0,
        'errors': 0,
        'api_calls': 0,
        'channels_updated': set()
    }

    if not videos:
        return stats

    print(f"\nUpdating statistics for {len(videos)} videos...")

    # Extract video IDs and track channels
    video_ids = [video['urn'] for video in videos]
    channels = set(video['author_username'] for video in videos if video.get('author_username'))

    # Fetch stats in batches
    batch_size = 50
    num_batches = (len(video_ids) + batch_size - 1) // batch_size
    print(f"Making {num_batches} API call(s) to YouTube...")

    video_stats = batch_fetch_video_stats(youtube, video_ids)
    stats['api_calls'] = num_batches

    # Create a mapping of urn to post_id
    video_map = {v['urn']: v for v in videos}

    # Insert new data_downloads records
    print(f"\nInserting stats snapshots...")
    for video_id, video_stat in video_stats.items():
        video = video_map.get(video_id)
        if not video:
            continue

        if insert_stats_snapshot(client, video['post_id'], video_id, video_stat):
            stats['updated'] += 1
            if video.get('author_username'):
                stats['channels_updated'].add(video['author_username'])
            if stats['updated'] % 10 == 0:
                print(f"  - Updated {stats['updated']}/{len(video_stats)} videos...")
        else:
            stats['errors'] += 1

    # Update last_synced_at for all channels that were updated
    if stats['channels_updated']:
        print(f"\nUpdating last_synced_at for {len(stats['channels_updated'])} channel(s)...")
        update_profile_sync_time(client, list(stats['channels_updated']))

    return stats


def show_statistics(client):
    """Display database statistics for YouTube content."""
    print("\n" + "=" * 70)
    print("YouTube Statistics")
    print("=" * 70)

    try:
        # YouTube post stats
        youtube_posts_result = client.table('posts').select('post_id', count='exact').eq('platform', 'youtube').execute()
        youtube_posts = youtube_posts_result.count if youtube_posts_result.count is not None else 0

        # Get YouTube videos with most snapshots
        snapshots_query = """
            SELECT p.post_id, p.url, p.author_username, COUNT(d.download_id) as snapshot_count
            FROM posts p
            LEFT JOIN data_downloads d ON p.post_id = d.post_id
            WHERE p.platform = 'youtube'
            GROUP BY p.post_id, p.url, p.author_username
            ORDER BY snapshot_count DESC
            LIMIT 5
        """

        # Recent YouTube runs
        recent_runs_result = client.table('download_runs').select(
            'run_id, started_at, completed_at, status, posts_fetched, posts_new, script_name'
        ).ilike('script_name', '%youtube%').order('started_at', desc=True).limit(5).execute()
        recent_runs = recent_runs_result.data

        print(f"\nOverall Statistics:")
        print(f"  Total YouTube Videos:  {youtube_posts:,}")

        if recent_runs:
            print(f"\nRecent YouTube Update Runs:")
            for run in recent_runs:
                run_id = run['run_id']
                started = run['started_at'][:19] if run.get('started_at') else 'N/A'
                status = run['status']
                fetched = run.get('posts_fetched', 0)
                script = run.get('script_name', 'N/A')
                status_symbol = "✓" if status == "completed" else "✗"
                print(f"  {status_symbol} {run_id} | {started} | {fetched} videos | {script}")

    except Exception as e:
        print(f"Error getting statistics: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update statistics for existing YouTube videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python update_youtube_stats.py                      # Update videos from last 30 days
  uv run python update_youtube_stats.py --days-back 7        # Update videos from last 7 days
  uv run python update_youtube_stats.py --limit 100          # Update only 100 most recent videos
  uv run python update_youtube_stats.py --all                # Update all YouTube videos
  uv run python update_youtube_stats.py --channel USERNAME   # Update specific channel only

Note: This script also updates the last_synced_at field for all YouTube profiles that were updated.
        """
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Update videos from last N days (default: 30)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of videos to update"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Update all YouTube videos regardless of age"
    )
    parser.add_argument(
        "--channel",
        help="Update only videos from specific channel username"
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Skip statistics display at the end"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.all and args.days_back != 30:
        print("Warning: --all flag will override --days-back setting")

    print("\n" + "=" * 70)
    print("YouTube Statistics Update")
    print("=" * 70)

    # Check API key
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY not found in .env file.")
        return 1

    # Initialize clients
    supabase_client = get_supabase_client()
    if not supabase_client:
        print("Failed to connect to Supabase. Check your .env file.")
        return 1

    youtube_service = get_youtube_service()
    if not youtube_service:
        print("Failed to initialize YouTube API service.")
        return 1

    # Create download run
    run_id = create_download_run(supabase_client, script_name="update_youtube_stats.py", platform="youtube")
    print(f"Created download run: {run_id}")

    # Query existing videos
    print("\n" + "=" * 70)
    print("Step 1: Querying Existing Videos")
    print("=" * 70)

    days_back = None if args.all else args.days_back
    videos = get_existing_youtube_videos(
        supabase_client,
        days_back=days_back,
        limit=args.limit,
        channel_username=args.channel
    )

    if not videos:
        print("No YouTube videos found matching criteria.")
        complete_download_run(supabase_client, run_id, {'processed': 0, 'new': 0, 'duplicates': 0, 'errors': 0})
        return 0

    print(f"Found {len(videos)} video(s) to update")
    if args.channel:
        print(f"  Channel: {args.channel}")
    if not args.all:
        print(f"  Date range: Last {args.days_back} days")
    else:
        print(f"  Date range: All videos")

    # Update statistics
    print("\n" + "=" * 70)
    print("Step 2: Fetching & Updating Statistics")
    print("=" * 70)

    update_stats = update_video_stats(supabase_client, youtube_service, videos, run_id)

    # Complete download run
    run_stats = {
        'processed': update_stats['total'],
        'new': update_stats['updated'],
        'duplicates': 0,
        'errors': update_stats['errors']
    }
    complete_download_run(supabase_client, run_id, run_stats)

    # Display summary
    print("\n" + "=" * 70)
    print("Update Summary")
    print("=" * 70)
    print(f"  Run ID:            {run_id}")
    print(f"  Videos Found:      {update_stats['total']}")
    print(f"  Stats Updated:     {update_stats['updated']}")
    print(f"  Channels Updated:  {len(update_stats.get('channels_updated', set()))}")
    print(f"  API Calls:         {update_stats['api_calls']}")
    print(f"  Errors:            {update_stats['errors']}")

    # Show statistics
    if not args.no_stats:
        show_statistics(supabase_client)

    print("\n" + "=" * 70)
    print("✓ Update completed successfully")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    exit(main())
