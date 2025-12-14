#!/usr/bin/env python3
"""
Script to fetch analytics (likes, comments) for Substack articles.

This script:
1. Fetches all active Substack profiles from the database.
2. For each profile, fetches its recent posts using the Substack API.
3. For each post, retrieves analytics data (likes, comments).
4. Updates the 'posts' table in Supabase with this new analytics data.

Usage:
    uv run python3 substack_analytics_fetcher.py
"""

import argparse
import sys
from datetime import datetime, timezone

from substack_api import Newsletter, Post
from supabase_client import get_supabase_client
from profile_manager import ProfileManager
from manage_data import create_download_run, complete_download_run

import time
from dateutil import parser as date_parser
from db_utils import generate_aws_id, PREFIX_POST

# Placeholder for actual analytics update function
# In a real scenario, this would interact with the Supabase client
# to update existing post entries with new like/comment counts.
# For now, it will just print the data.

def fetch_and_update_substack_analytics():
    """
    Fetches analytics for Substack posts and updates the database.
    """
    print("=" * 70)
    print("Fetching Substack Analytics")
    print("=" * 70)

    client = get_supabase_client()
    profile_manager = ProfileManager()

    # Create a download run entry
    run_id = create_download_run(client, script_name="substack_analytics_fetcher.py")
    print(f"Created download run: {run_id}")

    total_posts_processed = 0
    total_posts_updated = 0
    total_posts_created = 0
    total_posts_skipped = 0
    
    try:
        # Get active Substack profiles
        all_profiles = profile_manager.get_all_profiles(active_only=True)
        substack_profiles = [p for p in all_profiles if p.get('platform') == 'substack']

        if not substack_profiles:
            print("No active Substack profiles found to fetch analytics for.")
            complete_download_run(client, run_id, {'processed': 0, 'new': 0, 'duplicates': 0, 'errors': 0})
            return

        for profile in substack_profiles:
            username = profile.get('username')
            if not username:
                print(f"Skipping profile with missing username: {profile.get('name')}")
                continue

            print(f"\nProcessing Substack: {username}.substack.com")
            try:
                newsletter = Newsletter(f"https://{username}.substack.com")
                posts = newsletter.get_posts(limit=50) # Fetch recent posts

                for post_obj in posts:
                    total_posts_processed += 1
                    # Rate limiting protection
                    time.sleep(1)
                    
                    post_url = post_obj.url
                    # Use slug for URN if available, else fallback to extracting from URL
                    slug = getattr(post_obj, 'slug', None)
                    if not slug:
                        slug = post_url.rstrip('/').split('/')[-1]

                    post_urn = f"substack:{username}:{slug}"

                    print(f"  - Fetching metadata for: {post_url}")
                    try:
                        # Initialize Post object with URL, not just slug, for full metadata access
                        full_post = Post(post_url)
                        metadata = full_post.get_metadata()

                        likes_count = metadata.get('reactions', {}).get('❤', 0)
                        comments_count = metadata.get('comment_count', 0)

                        print(f"    Likes: {likes_count}, Comments: {comments_count}")

                        # Check if post exists
                        existing = client.table('posts').select('post_id').eq('urn', post_urn).execute()

                        if existing.data:
                            # Update existing post
                            response = client.table('posts').update({
                                'likes_count': likes_count,
                                'comments_count': comments_count,
                                'updated_at': datetime.now(timezone.utc).isoformat()
                            }).eq('urn', post_urn).execute()

                            if response.data:
                                print(f"    ✓ Updated analytics for URN: {post_urn}")
                                total_posts_updated += 1
                        else:
                            # Create new post (Backfill)
                            print(f"    + Creating new post for URN: {post_urn}")
                            
                            # Parse date
                            post_date_str = metadata.get('post_date')
                            if post_date_str:
                                dt = date_parser.parse(post_date_str)
                                posted_at_timestamp = int(dt.timestamp())
                            else:
                                posted_at_timestamp = int(datetime.now(timezone.utc).timestamp())

                            description = metadata.get('description', '') or metadata.get('subtitle', '')
                            title = metadata.get('title', '')
                            text_content = f"{title}\n\n{description}" if title else description

                            new_post = {
                                'post_id': generate_aws_id(PREFIX_POST),
                                'urn': post_urn,
                                'platform': 'substack',
                                'posted_at_timestamp': posted_at_timestamp,
                                'author_username': username,
                                'text_content': text_content,
                                'post_type': 'article',
                                'url': post_url,
                                'likes_count': likes_count,
                                'comments_count': comments_count,
                                'is_read': False,
                                'is_marked': False,
                                'created_at': datetime.now(timezone.utc).isoformat(),
                                'updated_at': datetime.now(timezone.utc).isoformat()
                            }
                            
                            client.table('posts').insert(new_post).execute()
                            total_posts_created += 1

                    except Exception as e:
                        print(f"    ✗ Error fetching or updating analytics for {post_url}: {e}")
                        # Optionally log this error to database
            except Exception as e:
                print(f"✗ Error processing newsletter {username}.substack.com: {e}")
                # Optionally log this error to database

    except Exception as e:
        print(f"An error occurred during analytics fetching: {e}")
    finally:
        # Complete the download run with overall statistics
        stats = {
            'processed': total_posts_processed,
            'new': total_posts_created,
            'duplicates': total_posts_skipped, # Count as skipped if not found/updated
            'errors': total_posts_processed - total_posts_updated - total_posts_created - total_posts_skipped, 
        }
        complete_download_run(client, run_id, stats)
        print("\nAnalytics Fetch Summary:")
        print(f"  Total Posts Processed: {total_posts_processed}")
        print(f"  Total Posts Updated:   {total_posts_updated}")
        print(f"  Total Posts Created:   {total_posts_created}")
        print(f"  Errors:                {stats['errors']}")
        print("\n✓ Substack Analytics fetching completed.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch Substack post analytics (likes, comments) and update the database."
    )
    # Add any specific arguments if needed in the future, similar to update_data.py
    args = parser.parse_args()

    fetch_and_update_substack_analytics()

if __name__ == "__main__":
    main()
