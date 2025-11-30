#!/usr/bin/env python3
"""
Unified data update script for social-tui.

This script:
1. Runs run_apify.sh to scrape latest LinkedIn data
2. Imports the scraped data into Supabase database
3. Shows updated statistics

Usage:
    python update_data.py
    python update_data.py --skip-scrape  # Only import existing data
    python update_data.py --date 20251129  # Import specific date
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from supabase_client import get_supabase_client
from manage_data import create_download_run, import_directory, complete_download_run


def run_apify_scrape():
    """Run the apify scraping script.

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


def get_todays_directory():
    """Get today's data directory path.

    Returns:
        Path object or None if directory doesn't exist
    """
    today = datetime.now().strftime("%Y%m%d")
    linkedin_dir = Path(f"data/{today}/linkedin")

    if linkedin_dir.exists():
        return linkedin_dir
    return None


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
        print("\n✓ Import completed successfully")

        return stats

    except Exception as e:
        print(f"\n✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def show_statistics():
    """Display database statistics."""
    print("\n" + "=" * 70)
    print("Step 3: Database Statistics")
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
        description="Update social-tui data (scrape + import + stats)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py                    # Full update (scrape + import + stats)
  python update_data.py --skip-scrape      # Import today's data only
  python update_data.py --date 20251129    # Import specific date
        """
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping step, only import existing data"
    )
    parser.add_argument(
        "--date",
        help="Import specific date directory (YYYYMMDD format)"
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Skip statistics display at the end"
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("Social-TUI Data Update")
    print("=" * 70)

    # Step 1: Scrape (unless skipped)
    if not args.skip_scrape:
        success = run_apify_scrape()
        if not success:
            print("\nWarning: Scraping failed, but will attempt to import existing data")
    else:
        print("\nSkipping scrape step (--skip-scrape)")

    # Step 2: Import
    if args.date:
        # Import specific date
        directory_path = Path(f"data/{args.date}/linkedin")
        if not directory_path.exists():
            print(f"\nError: Directory not found: {directory_path}")
            sys.exit(1)
    else:
        # Import today's data
        directory_path = get_todays_directory()
        if not directory_path:
            today = datetime.now().strftime("%Y%m%d")
            print(f"\nError: Today's data directory not found: data/{today}/linkedin")
            print("Run with --date YYYYMMDD to import a specific date")
            sys.exit(1)

    stats = import_data(directory_path)
    if stats is None:
        print("\n✗ Update failed")
        sys.exit(1)

    # Step 3: Stats (unless skipped)
    if not args.no_stats:
        show_statistics()

    print("\n" + "=" * 70)
    print("✓ Update completed successfully")
    print("=" * 70)


if __name__ == "__main__":
    main()
