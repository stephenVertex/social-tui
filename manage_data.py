#!/usr/bin/env python3
"""
Data management script for LinkedIn posts.
Handles ingestion of JSON files into Supabase database with deduplication.

Now uses Supabase with AWS-style identifiers and time-series tracking.
"""

import json
import glob
import argparse
import os
import socket
from pathlib import Path
from datetime import datetime

from supabase_client import get_supabase_client
from db_utils import generate_aws_id, PREFIX_POST, PREFIX_DOWNLOAD, PREFIX_RUN


def get_post_urn(post):
    """Extract the best URN from a post object."""
    urn = post.get('full_urn')
    if not urn and 'urn' in post:
        if isinstance(post['urn'], dict):
            urn = post['urn'].get('activity_urn') or post['urn'].get('ugcPost_urn')
        else:
            urn = post['urn']
    return urn


def create_download_run(client, script_name="import", platform="linkedin"):
    """Create a new download run record.

    Args:
        client: Supabase client
        script_name: Name of the script/process doing the import
        platform: Social media platform

    Returns:
        run_id: The ID of the created run
    """
    run_id = generate_aws_id(PREFIX_RUN)

    system_info = json.dumps({
        "hostname": socket.gethostname(),
        "platform": platform,
        "script": script_name,
    })

    client.table('download_runs').insert({
        'run_id': run_id,
        'started_at': datetime.now().isoformat(),
        'status': 'running',
        'script_name': script_name,
        'platform': platform,
        'system_info': system_info,
        'created_at': datetime.now().isoformat()
    }).execute()

    return run_id


def complete_download_run(client, run_id, stats, error_message=None):
    """Mark a download run as completed.

    Args:
        client: Supabase client
        run_id: The run ID to complete
        stats: Dictionary with stats (processed, new, duplicates, errors)
        error_message: Optional error message if run failed
    """
    status = 'failed' if error_message or stats['errors'] > 0 else 'completed'

    client.table('download_runs').update({
        'completed_at': datetime.now().isoformat(),
        'status': status,
        'posts_fetched': stats.get('processed', 0),
        'posts_new': stats.get('new', 0),
        'posts_updated': 0,  # posts_updated - we don't update in this version
        'error_message': error_message
    }).eq('run_id', run_id).execute()


def import_directory(client, directory, run_id=None):
    """Import all JSON files from a directory.

    Args:
        client: Supabase client
        directory: Directory containing JSON files
        run_id: Optional download run ID (will create one if not provided)

    Returns:
        Dictionary with import statistics and run_id
    """
    files = glob.glob(f"{directory}/*.json")
    print(f"Scanning {len(files)} files in {directory}...")

    # Create download run if not provided
    if run_id is None:
        run_id = create_download_run(client, script_name="manage_data.py")
        print(f"Created download run: {run_id}")

    stats = {
        "processed": 0,
        "new": 0,
        "duplicates": 0,
        "errors": 0
    }

    for fpath in files:
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)

            if not isinstance(data, list):
                # Handle single object files if necessary
                if isinstance(data, dict):
                    data = [data]
                else:
                    continue

            for post in data:
                stats["processed"] += 1
                urn = get_post_urn(post)

                if not urn:
                    print(f"Warning: No URN found for post in {fpath}")
                    stats["errors"] += 1
                    continue

                # Check if post already exists
                existing_result = client.table('posts').select('post_id').eq('urn', urn).execute()
                existing = existing_result.data

                if existing:
                    # Post exists - create a new data_download entry for time-series
                    post_id = existing[0]['post_id']
                    stats["duplicates"] += 1
                else:
                    # New post - create post and data_download
                    post_id = generate_aws_id(PREFIX_POST)

                    # Extract metadata for columns
                    author = post.get('author', {})
                    username = author.get('username', '')
                    text = post.get('text', '')
                    posted_at = post.get('posted_at', {})
                    timestamp = posted_at.get('timestamp')
                    post_type = post.get('post_type', 'regular')
                    url = post.get('url')

                    try:
                        client.table('posts').insert({
                            'post_id': post_id,
                            'urn': urn,
                            'full_urn': post.get('full_urn'),
                            'platform': 'linkedin',
                            'posted_at_timestamp': timestamp,
                            'author_username': username,
                            'text_content': text,
                            'post_type': post_type,
                            'url': url,
                            'raw_json': json.dumps(post),
                            'first_seen_at': datetime.now().isoformat(),
                            'is_read': False,
                            'is_marked': False,
                            'created_at': datetime.now().isoformat(),
                            'updated_at': datetime.now().isoformat()
                        }).execute()
                        stats["new"] += 1
                    except Exception as e:
                        print(f"Error inserting post {urn}: {e}")
                        stats["errors"] += 1
                        continue

                # Create data_download entry (for both new and existing posts)
                download_id = generate_aws_id(PREFIX_DOWNLOAD)

                # Extract stats
                stats_data = post.get('stats', {})
                total_reactions = stats_data.get('total_reactions', 0)

                try:
                    client.table('data_downloads').insert({
                        'download_id': download_id,
                        'post_id': post_id,
                        'run_id': run_id,
                        'downloaded_at': datetime.now().isoformat(),
                        'total_reactions': total_reactions,
                        'stats_json': json.dumps(stats_data),
                        'raw_json': json.dumps(post),
                        'source_file_path': fpath,
                        'created_at': datetime.now().isoformat()
                    }).execute()
                except Exception as e:
                    print(f"Error creating data_download for {urn}: {e}")
                    stats["errors"] += 1

        except Exception as e:
            print(f"Error processing {fpath}: {e}")
            stats["errors"] += 1

    return stats, run_id


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Manage LinkedIn posts data")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import JSON files")
    import_parser.add_argument("directory", help="Directory containing JSON files")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")

    args = parser.parse_args()

    client = get_supabase_client()

    try:
        if args.command == "import":
            if os.path.isdir(args.directory):
                stats, run_id = import_directory(client, args.directory)

                # Complete the download run
                complete_download_run(client, run_id, stats)

                print("\nImport Summary:")
                print(f"Run ID:     {run_id}")
                print(f"Processed:  {stats['processed']}")
                print(f"New:        {stats['new']}")
                print(f"Duplicates: {stats['duplicates']}")
                print(f"Errors:     {stats['errors']}")
            else:
                print(f"Error: Directory not found: {args.directory}")

        elif args.command == "stats":
            # Post stats
            total_posts_result = client.table('posts').select('post_id', count='exact').execute()
            total_posts = total_posts_result.count if total_posts_result.count is not None else 0

            marked_result = client.table('posts').select('post_id', count='exact').eq('is_marked', True).execute()
            marked = marked_result.count if marked_result.count is not None else 0

            # Download stats
            total_downloads_result = client.table('data_downloads').select('download_id', count='exact').execute()
            total_downloads = total_downloads_result.count if total_downloads_result.count is not None else 0

            total_runs_result = client.table('download_runs').select('run_id', count='exact').execute()
            total_runs = total_runs_result.count if total_runs_result.count is not None else 0

            print(f"\nDatabase Statistics:")
            print(f"Total Posts:     {total_posts}")
            print(f"Marked Posts:    {marked}")
            print(f"Data Downloads:  {total_downloads}")
            print(f"Download Runs:   {total_runs}")

            # Note: Supabase doesn't support GROUP BY date() function directly
            # We'd need to fetch all posts and group them in Python if needed
            print(f"\nIngestion History: (not implemented for Supabase)")

        else:
            parser.print_help()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
