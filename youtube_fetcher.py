#!/usr/bin/env python3
"""
Fetches new videos from monitored YouTube channels using the YouTube Data API
and saves them to the Supabase database.
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase_client import get_supabase_client
from media_cache import download_and_cache_media

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

def get_active_youtube_channels(client):
    """Retrieves a list of active YouTube channels from the profiles table."""
    try:
        response = client.table('profiles').select('*').eq('platform', 'youtube').eq('is_active', True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching active YouTube channels: {e}")
        return []

def get_channel_uploads_playlist_id(youtube, channel_username):
    """Gets the ID of the 'uploads' playlist for a given channel username."""
    try:
        # The username might not be the channel's custom URL handle, so we search for it
        search_response = youtube.search().list(
            q=channel_username,
            type="channel",
            part="id,snippet",
            maxResults=1
        ).execute()

        if not search_response.get("items"):
            print(f"  - No channel found for username: {channel_username}")
            return None
        
        channel_id = search_response["items"][0]["id"]["channelId"]
        
        channels_response = youtube.channels().list(
            id=channel_id,
            part="contentDetails"
        ).execute()

        if not channels_response.get("items"):
            print(f"  - Could not get channel details for ID: {channel_id}")
            return None
            
        return channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except HttpError as e:
        print(f"  - An HTTP error {e.resp.status} occurred: {e.content}")
        return None


def fetch_new_videos_from_playlist(youtube, playlist_id, published_after):
    """Fetches new videos from a playlist published after a specific date."""
    videos = []
    next_page_token = None
    
    try:
        while True:
            playlist_response = youtube.playlistItems().list(
                playlistId=playlist_id,
                part="snippet",
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            video_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist_response["items"]]

            if not video_ids:
                break
            
            videos_response = youtube.videos().list(
                id=",".join(video_ids),
                part="snippet,statistics,contentDetails"
            ).execute()

            for item in videos_response["items"]:
                published_at_dt = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
                if published_at_dt >= published_after:
                    videos.append(item)

            # Check if the last video on the page is older than our cutoff
            last_video_published_at = datetime.fromisoformat(
                videos_response["items"][-1]["snippet"]["publishedAt"].replace("Z", "+00:00")
            )
            if last_video_published_at < published_after:
                break # All subsequent videos will be older

            next_page_token = playlist_response.get("nextPageToken")
            if not next_page_token:
                break
                
        return videos
    except HttpError as e:
        print(f"  - An HTTP error {e.resp.status} occurred: {e.content}")
        return []

def insert_new_video(client, video_data, channel):
    """Inserts a new video into the database if it doesn't already exist."""
    video_id = video_data.get('id')
    if not video_id:
        return False

    try:
        response = client.table('posts').select('post_id').eq('urn', video_id).execute()
        if response.data:
            return False
    except Exception as e:
        print(f"  - Error checking for existing video: {e}")
        return False

    print(f"  - Inserting new video: {video_data['snippet'].get('title')}")

    post_id = f"p-{uuid.uuid4().hex[:8]}"
    published_at = datetime.fromisoformat(video_data['snippet']['publishedAt'].replace("Z", "+00:00"))
    stats = video_data.get('statistics', {})

    post_record = {
        'post_id': post_id,
        'urn': video_id,
        'full_urn': f"youtube:video:{video_id}",
        'platform': 'youtube',
        'posted_at_timestamp': int(published_at.timestamp() * 1000),
        'author_username': channel.get('username'),
        'text_content': f"{video_data['snippet'].get('title', '')}\n\n{video_data['snippet'].get('description', '')}",
        'url': f"https://www.youtube.com/watch?v={video_id}",
        'raw_json': json.dumps(video_data),
        'first_seen_at': datetime.now(timezone.utc).isoformat(),
    }
    
    media_records = []

    # 1. Video Media Record
    media_id_video = f"med-{uuid.uuid4().hex[:8]}"
    media_record_video = {
        'media_id': media_id_video,
        'post_id': post_id,
        'media_type': 'video',
        'media_url': f"https://www.youtube.com/watch?v={video_id}",
        'local_file_path': None,
    }
    media_records.append(media_record_video)

    # 2. Thumbnail Media Record
    thumbnail_url = video_data['snippet']['thumbnails'].get('high', {}).get('url')
    if thumbnail_url:
        try:
            print(f"    - Downloading thumbnail: {thumbnail_url}")
            # Download and cache the thumbnail
            cache_result = download_and_cache_media(thumbnail_url, media_type='image')

            media_id_thumb = f"med-{uuid.uuid4().hex[:8]}"
            media_record_thumb = {
                'media_id': media_id_thumb,
                'post_id': post_id,
                'media_type': 'image',
                'media_url': thumbnail_url,
                'local_file_path': str(cache_result['local_path']),
                'width': cache_result.get('width'),
                'height': cache_result.get('height')
            }
            media_records.append(media_record_thumb)
        except Exception as e:
            print(f"    - Error downloading thumbnail: {e}")
            # If download fails, we can optionally insert it without local path or skip
            # For now, let's insert it without local path so we at least have the URL
            media_id_thumb = f"med-{uuid.uuid4().hex[:8]}"
            media_record_thumb = {
                'media_id': media_id_thumb,
                'post_id': post_id,
                'media_type': 'image',
                'media_url': thumbnail_url,
                'local_file_path': None
            }
            media_records.append(media_record_thumb)

    # Create a record for the time-series data
    download_id = f"d-{uuid.uuid4().hex[:8]}"
    data_download_record = {
        'download_id': download_id,
        'post_id': post_id,
        'downloaded_at': datetime.now(timezone.utc).isoformat(),
        'total_reactions': int(stats.get('likeCount', 0)), # Using likes as reactions
        'stats_json': json.dumps({
            'views': int(stats.get('viewCount', 0)),
            'likes': int(stats.get('likeCount', 0)),
            'comments': int(stats.get('commentCount', 0)),
        })
    }
    
    try:
        client.table('posts').insert(post_record).execute()
        if media_records:
            client.table('post_media').insert(media_records).execute()
        client.table('data_downloads').insert(data_download_record).execute()
        return True
    except Exception as e:
        print(f"    - Error inserting video into database: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Fetch new videos from YouTube channels using the YouTube Data API.")
    parser.add_argument(
        "--days-back",
        type=int,
        default=5,
        help="Number of days back to check for new videos."
    )
    args = parser.parse_args()

    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY not found in .env file.")
        return

    supabase_client = get_supabase_client()
    if not supabase_client:
        print("Failed to connect to Supabase. Check your .env file.")
        return
        
    youtube_service = get_youtube_service()
    if not youtube_service:
        return

    channels = get_active_youtube_channels(supabase_client)
    if not channels:
        print("No active YouTube channels found in the 'profiles' table.")
        return

    print(f"Found {len(channels)} active channel(s).")
    new_videos_total = 0
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days_back)
    print(f"Fetching videos published on or after: {cutoff_date.strftime('%Y-%m-%d')}")

    for channel in channels:
        channel_name = channel.get('name', 'N/A')
        channel_username = channel.get('username')
        print(f"\n--- Processing channel: {channel_name} ({channel_username}) ---")

        uploads_playlist_id = get_channel_uploads_playlist_id(youtube_service, channel_username)
        if not uploads_playlist_id:
            print(f"  - Could not find uploads playlist for {channel_name}. Skipping.")
            continue
            
        print(f"  - Found uploads playlist ID: {uploads_playlist_id}")
        
        videos = fetch_new_videos_from_playlist(youtube_service, uploads_playlist_id, cutoff_date)
        if not videos:
            print("  - No new videos found for this channel in the given time frame.")
            continue

        print(f"  - Fetched {len(videos)} recent videos. Checking for new content...")
        new_videos_count = 0
        for video in reversed(videos): # Insert oldest first
            if insert_new_video(supabase_client, video, channel):
                new_videos_count += 1
        
        if new_videos_count > 0:
            print(f"  -> Inserted {new_videos_count} new video(s) for {channel_name}.")
            new_videos_total += new_videos_count
        else:
            print("  -> No new videos found to insert for this channel.")

    print(f"\nFinished processing all channels. Inserted a total of {new_videos_total} new videos.")

if __name__ == "__main__":
    main()