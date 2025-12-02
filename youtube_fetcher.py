#!/usr/bin/env python3
"""
Fetches new videos from monitored YouTube channels and saves them to the Supabase database.
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from supabase_client import get_supabase_client

import uuid

def get_active_youtube_channels(client):
    """
    Retrieves a list of active YouTube channels from the profiles table.

    Args:
        client: The Supabase client.

    Returns:
        A list of profile records for active YouTube channels.
    """
    try:
        response = client.table('profiles').select('*').eq('platform', 'youtube').eq('is_active', True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching active YouTube channels: {e}")
        return []

def fetch_videos_for_channel(channel_url, num_videos=10):
    """
    Fetches the latest videos for a given YouTube channel using yt-dlp.

    Args:
        channel_url: The URL of the YouTube channel.
        num_videos: The number of recent videos to fetch.

    Returns:
        A list of dictionaries, where each dictionary represents a video's metadata.
    """
    try:
        # Step 1: Get a list of video IDs from the channel's main video feed
        # Using --extractor-args youtube:tab=videos to explicitly target the videos tab
        list_command = [
            'yt-dlp',
            '--flat-playlist',
            '--print-json',
            '--extractor-args', 'youtube:tab=videos',
            '--playlist-end', str(num_videos), # Limit to 'num_videos' directly here for efficiency
            channel_url
        ]
        list_result = subprocess.run(list_command, capture_output=True, text=True, check=True)
        
        video_ids_to_fetch = []
        for line in list_result.stdout.strip().split('\n'):
            if line:
                try:
                    meta = json.loads(line)
                    if meta.get('_type') == 'url' and meta.get('id'):
                        video_ids_to_fetch.append(meta['id'])
                except json.JSONDecodeError:
                    continue
        
        if not video_ids_to_fetch:
            print(f"  - No video IDs found for {channel_url} using tab=videos extractor.")
            
            # Fallback: try without explicit tab for broader compatibility
            list_command_fallback = [
                'yt-dlp',
                '--flat-playlist',
                '--print-json',
                '--playlist-end', str(num_videos),
                channel_url
            ]
            list_result_fallback = subprocess.run(list_command_fallback, capture_output=True, text=True, check=True)
            for line in list_result_fallback.stdout.strip().split('\n'):
                if line:
                    try:
                        meta = json.loads(line)
                        if meta.get('_type') == 'url' and meta.get('id'):
                            video_ids_to_fetch.append(meta['id'])
                    except json.JSONDecodeError:
                        continue
            if not video_ids_to_fetch:
                print(f"  - No video IDs found for {channel_url} with fallback method.")
                return []
            else:
                print(f"  - Found {len(video_ids_to_fetch)} video IDs using fallback method.")

        # Step 2: Fetch full metadata for each video ID
        videos_metadata = []
        for video_id in video_ids_to_fetch:
            detail_command = [
                'yt-dlp',
                '--dump-json',
                f"https://www.youtube.com/watch?v={video_id}"
            ]
            detail_result = subprocess.run(detail_command, capture_output=True, text=True, check=True)
            videos_metadata.append(json.loads(detail_result.stdout))
            
        return videos_metadata

    except FileNotFoundError:
        print("Error: yt-dlp is not installed or not in your PATH.")
        print("Please install it: https://github.com/yt-dlp/yt-dlp")
        return []
    except subprocess.CalledProcessError as e:
        print(f"Error executing yt-dlp for {channel_url}: {e}")
        print(f"Stderr: {e.stderr}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while fetching videos for {channel_url}: {e}")
        return []
def insert_new_video(client, video_data, channel):
    """
    Inserts a new video into the posts and post_media tables if it doesn't exist.

    Args:
        client: The Supabase client.
        video_data: A dictionary of video metadata from yt-dlp.
        channel: The channel profile from the database.
    
    Returns:
        True if a new video was inserted, False otherwise.
    """
    video_id = video_data.get('id')
    if not video_id:
        return False

    # Check if video already exists
    try:
        response = client.table('posts').select('post_id').eq('urn', video_id).execute()
        if response.data:
            # print(f"  - Video '{video_data.get('title')}' already exists. Skipping.")
            return False
    except Exception as e:
        print(f"  - Error checking for existing video: {e}")
        return False

    print(f"  - Inserting new video: {video_data.get('title')}")

    # Generate a new post_id
    post_id = f"p-{uuid.uuid4().hex[:12]}"

    # Prepare data for 'posts' table
    posted_at_raw = video_data.get('timestamp', datetime.now().timestamp())
    posted_at = datetime.fromtimestamp(posted_at_raw, tz=timezone.utc)

    # Filter out videos older than 2025-11-26
    cutoff_date = datetime(2025, 11, 26, 0, 0, 0, tzinfo=timezone.utc) # UTC for comparison
    if posted_at < cutoff_date:
        print(f"  - Video '{video_data.get('title')}' posted on {posted_at.date()} is older than {cutoff_date.date()}. Skipping.")
        return False
    
    post_record = {
        'post_id': post_id,
        'urn': video_id,
        'full_urn': f"youtube:video:{video_id}",
        'platform': 'youtube',
        'posted_at_timestamp': int(posted_at.timestamp()),
        'author_username': channel.get('username'),
        'text_content': f"{video_data.get('title', '')}\n\n{video_data.get('description', '')}",
        'url': video_data.get('webpage_url'),
        'raw_json': json.dumps(video_data),
        'first_seen_at': datetime.now(timezone.utc).isoformat(),
    }

    # Prepare data for 'post_media' table
    media_id = f"pm-{uuid.uuid4().hex[:12]}"
    thumbnail = video_data.get('thumbnail')
    
    media_record = {
        'media_id': media_id,
        'post_id': post_id,
        'media_type': 'video',
        'media_url': video_data.get('webpage_url'),
        'local_file_path': thumbnail, # Store thumbnail URL here for now
        'width': video_data.get('width'),
        'height': video_data.get('height'),
    }

    try:
        # Insert into posts table
        client.table('posts').insert(post_record).execute()

        # Insert into post_media table
        client.table('post_media').insert(media_record).execute()
        
        return True
    except Exception as e:
        print(f"    - Error inserting video into database: {e}")
        return False


def main():
    """Main function to run the YouTube video fetcher."""
    parser = argparse.ArgumentParser(description="Fetch new videos from YouTube channels.")
    parser.add_argument(
        "--num-videos",
        type=int,
        default=10,
        help="Number of recent videos to check for each channel."
    )
    args = parser.parse_args()

    print("Connecting to Supabase...")
    client = get_supabase_client()
    if not client:
        print("Failed to connect to Supabase. Check your .env file.")
        return

    print("Fetching active YouTube channels...")
    channels = get_active_youtube_channels(client)
    if not channels:
        print("No active YouTube channels found in the 'profiles' table.")
        return

    print(f"Found {len(channels)} active channel(s).")
    new_videos_total = 0

    for channel in channels:
        channel_name = channel.get('name', 'N/A')
        channel_username = channel.get('username')
        channel_url = f"https://www.youtube.com/{channel_username}"
        print(f"\n--- Processing channel: {channel_name} ({channel_url}) ---")

        videos = fetch_videos_for_channel(channel_url, args.num_videos)
        if not videos:
            print("No videos found or an error occurred.")
            continue

        print(f"Fetched {len(videos)} recent videos. Checking for new content...")
        new_videos_count = 0

        for video in videos:
            if insert_new_video(client, video, channel):
                new_videos_count += 1
        
        if new_videos_count > 0:
            print(f"  -> Inserted {new_videos_count} new video(s) for {channel_name}.")
            new_videos_total += new_videos_count
        else:
            print("  -> No new videos found for this channel.")

    print(f"\nFinished processing all channels. Inserted a total of {new_videos_total} new videos.")


if __name__ == "__main__":
    main()
