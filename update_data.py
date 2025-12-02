#!/usr/bin/env python3
"""
Unified data update script for social-tui.

This script:
1. Runs run_apify.sh to scrape latest LinkedIn data
2. Imports the scraped data into Supabase database
3. Uploads newly cached media to S3
4. Shows updated statistics

Usage:
    python update_data.py                    # Full update
    python update_data.py --skip-scrape      # Only import existing data
    python update_data.py --skip-s3-upload   # Skip S3 upload
    python update_data.py --date 20251129    # Import specific date
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from supabase_client import get_supabase_client
from manage_data import create_download_run, import_directory, complete_download_run
from scripts.s3_upload.upload_to_s3 import upload_media_to_s3


def run_apify_scrape(data_dir=None):
    """Run the apify scraping script.

    Args:
        data_dir: Optional directory path to use (for retry). If None, creates new timestamped directory.

    Returns:
        True if successful, False otherwise
    """
    print("=" * 70)
    print("Step 1: Scraping LinkedIn Data")
    print("=" * 70)

    script_path = Path("run_apify.sh")
    if not script_path.exists():
        print(f"Error: {script_path} not found")
        return False

    try:
        # Run the script and stream output
        if data_dir:
            print(f"Retrying with directory: {data_dir}")
            result = subprocess.run(
                ["bash", str(script_path), str(data_dir)],
                check=True,
                text=True
            )
        else:
            result = subprocess.run(
                ["bash", str(script_path)],
                check=True,
                text=True
            )
        print("\n✓ Scraping completed successfully")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Scraping failed with exit code {e.returncode}")
        return False
    except Exception as e:
        print(f"\n✗ Scraping failed: {e}")
        return False


def get_most_recent_directory(date_filter=None):
    """Get the most recent data directory path.

    Args:
        date_filter: Optional date string (YYYYMMDD) to filter directories. If None, gets most recent overall.

    Returns:
        Path object or None if no directory found
    """
    data_path = Path("data")
    if not data_path.exists():
        return None

    # Find all directories matching the pattern
    if date_filter:
        # Look for directories starting with the date (both old and new formats)
        pattern = f"{date_filter}*"
    else:
        # Look for all date directories (YYYYMMDD or YYYYMMDD_HHMMSS)
        pattern = "*"

    matching_dirs = []
    for dir_path in data_path.glob(pattern):
        if dir_path.is_dir():
            linkedin_dir = dir_path / "linkedin"
            if linkedin_dir.exists():
                matching_dirs.append(linkedin_dir)

    if not matching_dirs:
        return None

    # Sort by directory name (timestamp embedded in name) and return most recent
    matching_dirs.sort(reverse=True)
    return matching_dirs[0]


def get_todays_directory():
    """Get today's most recent data directory path.

    Returns:
        Path object or None if directory doesn't exist
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return get_most_recent_directory(date_filter=today)


def get_last_run_time():
    """Get the timestamp of the most recent run.

    Returns:
        datetime object or None if no runs found
    """
    most_recent = get_most_recent_directory()
    if not most_recent:
        return None

    # Extract timestamp from directory path
    # Format: data/YYYYMMDD_HHMMSS/linkedin or data/YYYYMMDD/linkedin
    parent_name = most_recent.parent.name

    try:
        # Try new format: YYYYMMDD_HHMMSS
        if "_" in parent_name:
            timestamp_str = parent_name
            return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        else:
            # Old format: YYYYMMDD (assume end of day)
            return datetime.strptime(parent_name, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def check_rate_limit(force=False):
    """Check if the script was run recently and prompt user.

    Args:
        force: If True, skip the check

    Returns:
        True if should proceed, False if should exit
    """
    if force:
        return True

    last_run = get_last_run_time()
    if not last_run:
        return True

    now = datetime.now(timezone.utc)
    hours_since_last_run = (now - last_run).total_seconds() / 3600

    if hours_since_last_run < 2:
        print("\n" + "⚠" * 35)
        print("WARNING: Rate Limit Check")
        print("⚠" * 35)
        print(f"\nLast run was {hours_since_last_run:.1f} hours ago at {last_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("Running too frequently may abuse the Apify API.")
        print("\nOptions:")
        print("  1. Continue anyway")
        print("  2. Cancel (recommended)")
        print("  3. Use --force flag to bypass this check in the future")
        print("  4. Use --retry to retry the last run instead")

        response = input("\nDo you want to continue? (y/N): ").strip().lower()
        if response not in ["y", "yes"]:
            print("\nCancelled. Use --retry to retry the last run, or wait before running again.")
            return False

    return True


def import_data(directory_path):
    """Import data from a directory.

    Args:
        directory_path: Path to directory containing JSON files

    Returns:
        Dictionary with import statistics or None if failed
    """
    print("\n" + "=" * 70)
    print("Step 2: Importing Data to Database")
    print("=" * 70)
    print(f"Directory: {directory_path}")

    if not directory_path.exists():
        print(f"Error: Directory not found: {directory_path}")
        return None

    # Count files
    json_files = list(directory_path.glob("*.json"))
    if not json_files:
        print(f"Warning: No JSON files found in {directory_path}")
        return {"processed": 0, "new": 0, "duplicates": 0, "errors": 0}

    print(f"Found {len(json_files)} JSON files")

    try:
        client = get_supabase_client()

        # Create download run
        run_id = create_download_run(client, script_name="update_data.py")
        print(f"Created download run: {run_id}")

        # Import directory
        stats, _ = import_directory(client, str(directory_path), run_id=run_id)

        # Complete download run
        complete_download_run(client, run_id, stats)

        print("\nImport Summary:")
        print(f"  Run ID:     {run_id}")
        print(f"  Processed:  {stats['processed']}")
        print(f"  New:        {stats['new']}")
        print(f"  Duplicates: {stats['duplicates']}")
        print(f"  Errors:     {stats['errors']}")
        print(f"\n  Media:")
        print(f"    Found:    {stats.get('media_total', 0)}")
        print(f"    Cached:   {stats.get('media_cached', 0)}")
        print(f"    Errors:   {stats.get('media_errors', 0)}")
        print("\n✓ Import completed successfully")

        return stats

    except Exception as e:
        print(f"\n✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def upload_to_s3():
    """Upload newly cached media to S3."""
    print("\n" + "=" * 70)
    print("Step 3: Uploading Media to S3")
    print("=" * 70)

    try:
        stats = upload_media_to_s3(dry_run=False, batch_size=50)

        if stats['uploads_attempted'] > 0:
            print(f"\nS3 Upload Summary:")
            print(f"  Files Found:     {stats['files_found']}")
            print(f"  Uploads:         {stats['uploads_successful']}/{stats['uploads_attempted']}")
            print(f"  DB Updates:      {stats['db_updates_successful']}/{stats['uploads_successful']}")

            if stats['uploads_failed'] > 0 or stats['db_updates_failed'] > 0:
                print(f"\n⚠ Some uploads had errors (see logs above)")
            else:
                print(f"\n✓ S3 upload completed successfully")
        else:
            print("\n✓ No new media to upload")

        return stats

    except Exception as e:
        print(f"\n✗ S3 upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def show_statistics():
    """Display database statistics."""
    print("\n" + "=" * 70)
    print("Step 4: Database Statistics")
    print("=" * 70)

    try:
        client = get_supabase_client()

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

        # Recent runs
        recent_runs_result = client.table('download_runs').select(
            'run_id, started_at, completed_at, status, posts_fetched, posts_new'
        ).order('started_at', desc=True).limit(5).execute()
        recent_runs = recent_runs_result.data

        print(f"\nOverall Statistics:")
        print(f"  Total Posts:     {total_posts:,}")
        print(f"  Marked Posts:    {marked:,}")
        print(f"  Data Downloads:  {total_downloads:,}")
        print(f"  Download Runs:   {total_runs:,}")

        if recent_runs:
            print(f"\nRecent Download Runs:")
            for run in recent_runs:
                run_id = run['run_id']
                started = run['started_at'][:19] if run.get('started_at') else 'N/A'
                completed = run['completed_at'][:19] if run.get('completed_at') else 'N/A'
                status = run['status']
                fetched = run.get('posts_fetched', 0)
                new = run.get('posts_new', 0)
                status_symbol = "✓" if status == "completed" else "✗"
                print(f"  {status_symbol} {run_id} | {started} | {fetched} posts ({new} new)")

    except Exception as e:
        print(f"Error getting statistics: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update social-tui data (scrape + import + S3 upload + stats)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py                      # Full update (scrape + import + S3 + stats)
  python update_data.py --skip-scrape        # Import today's data only (+ S3 + stats)
  python update_data.py --skip-s3-upload     # Update without S3 upload
  python update_data.py --date 20251129      # Import specific date (most recent run)
  python update_data.py --retry              # Retry most recent run (scrape missing + import)
  python update_data.py --force              # Bypass 2-hour rate limit check
        """
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping step, only import existing data"
    )
    parser.add_argument(
        "--date",
        help="Import specific date directory (YYYYMMDD format, uses most recent run for that date)"
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Retry the most recent run (scrape any missing files and import)"
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Skip statistics display at the end"
    )
    parser.add_argument(
        "--skip-s3-upload",
        action="store_true",
        help="Skip S3 upload of newly cached media"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run without rate limit check (bypass 2-hour warning)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.retry and args.date:
        print("Error: Cannot use --retry and --date together")
        sys.exit(1)
    if args.retry and args.skip_scrape:
        print("Error: Cannot use --retry and --skip-scrape together")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("Social-TUI Data Update")
    print("=" * 70)

    # Check rate limit for new runs (not retry, not skip-scrape)
    if not args.retry and not args.skip_scrape:
        if not check_rate_limit(force=args.force):
            sys.exit(0)

    # Determine directory to use
    retry_directory = None
    if args.retry:
        # Find most recent directory for retry
        retry_directory = get_most_recent_directory()
        if not retry_directory:
            print("\nError: No existing data directories found to retry")
            sys.exit(1)
        print(f"\nRetrying most recent run: {retry_directory.parent}")

    # Step 1: Scrape (unless skipped)
    if not args.skip_scrape:
        if args.retry:
            # Retry: use existing directory
            success = run_apify_scrape(data_dir=retry_directory)
        else:
            # Normal run: create new directory
            success = run_apify_scrape()

        if not success:
            print("\nWarning: Scraping failed, but will attempt to import existing data")
    else:
        print("\nSkipping scrape step (--skip-scrape)")

    # Step 2: Import
    if args.retry:
        # Use the retry directory
        directory_path = retry_directory
    elif args.date:
        # Import specific date (most recent run for that date)
        directory_path = get_most_recent_directory(date_filter=args.date)
        if not directory_path:
            print(f"\nError: No data directory found for date: {args.date}")
            print(f"Looked for directories matching: data/{args.date}*/linkedin")
            sys.exit(1)
        print(f"\nUsing directory: {directory_path}")
    else:
        # Import today's data (most recent run for today)
        directory_path = get_todays_directory()
        if not directory_path:
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            print(f"\nError: Today's data directory not found")
            print(f"Looked for directories matching: data/{today}*/linkedin")
            print("Run with --date YYYYMMDD to import a specific date")
            sys.exit(1)

    stats = import_data(directory_path)
    if stats is None:
        print("\n✗ Update failed")
        sys.exit(1)

    # Step 3: Upload to S3 (unless skipped)
    if not args.skip_s3_upload:
        s3_stats = upload_to_s3()
        if s3_stats is None:
            print("\n⚠ S3 upload failed, but continuing...")
    else:
        print("\nSkipping S3 upload (--skip-s3-upload)")

    # Step 4: Stats (unless skipped)
    if not args.no_stats:
        show_statistics()

    print("\n" + "=" * 70)
    print("✓ Update completed successfully")
    print("=" * 70)


if __name__ == "__main__":
    main()
