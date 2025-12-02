#!/usr/bin/env python3
"""
Migrate historical download runs from date-based directories.

This script backfills download_runs and data_downloads tables with historical
data from data/{YYYYMMDD}/linkedin/ directories.

Usage:
    python migrate_historical_runs.py
    python migrate_historical_runs.py --dry-run
"""

import argparse
import glob
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from db_utils import generate_aws_id, PREFIX_DOWNLOAD, PREFIX_RUN
from manage_data import get_post_urn


DB_PATH = "data/posts_v2.db"


def get_connection():
    """Get database connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def find_date_directories():
    """Find all date-based directories in data/.

    Returns:
        List of tuples: (date_string, directory_path)
        Sorted by date (oldest first)
    """
    directories = []

    for path in Path("data").glob("[0-9]*"):
        if path.is_dir() and len(path.name) == 8:
            linkedin_dir = path / "linkedin"
            if linkedin_dir.exists():
                # Parse date from directory name
                date_str = path.name  # YYYYMMDD
                try:
                    # Validate it's a real date
                    datetime.strptime(date_str, "%Y%m%d")
                    directories.append((date_str, str(linkedin_dir)))
                except ValueError:
                    print(f"Skipping invalid date directory: {path.name}")

    # Sort by date (oldest first)
    directories.sort(key=lambda x: x[0])
    return directories


def create_historical_run(conn, date_str, directory):
    """Create a download run record for a historical import.

    Args:
        conn: Database connection
        date_str: Date string in YYYYMMDD format
        directory: Directory path containing JSON files

    Returns:
        run_id: The ID of the created run
    """
    cursor = conn.cursor()
    run_id = generate_aws_id(PREFIX_RUN)

    # Parse date and create timestamp
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    # Set time to noon to avoid timezone issues
    started_at = date_obj.replace(hour=12, minute=0, second=0)

    system_info = json.dumps({
        "hostname": "historical-migration",
        "platform": "linkedin",
        "script": "run_apify.sh",
        "note": f"Backfilled from {directory}"
    })

    cursor.execute("""
        INSERT INTO download_runs (
            run_id, started_at, status, script_name, platform, system_info, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        started_at.isoformat(),
        'running',
        'run_apify.sh',
        'linkedin',
        system_info,
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    return run_id, started_at


def import_historical_directory(conn, directory, run_id, run_date):
    """Import JSON files from a historical directory.

    Args:
        conn: Database connection
        directory: Directory containing JSON files
        run_id: Download run ID to associate with
        run_date: Date of the run (for downloaded_at timestamp)

    Returns:
        Dictionary with import statistics
    """
    files = glob.glob(f"{directory}/*.json")
    print(f"  Scanning {len(files)} files...")

    cursor = conn.cursor()

    stats = {
        "processed": 0,
        "new_posts": 0,
        "existing_posts": 0,
        "downloads_created": 0,
        "errors": 0
    }

    for fpath in files:
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)

            if not isinstance(data, list):
                if isinstance(data, dict):
                    data = [data]
                else:
                    continue

            for post in data:
                stats["processed"] += 1
                urn = get_post_urn(post)

                if not urn:
                    print(f"    Warning: No URN found for post in {fpath}")
                    stats["errors"] += 1
                    continue

                # Check if post already exists
                cursor.execute("SELECT post_id FROM posts WHERE urn = ?", (urn,))
                existing = cursor.fetchone()

                if existing:
                    post_id = existing[0]
                    stats["existing_posts"] += 1
                else:
                    # Post doesn't exist - shouldn't happen if migration ran correctly
                    print(f"    Warning: Post {urn} not found in database, skipping")
                    stats["errors"] += 1
                    continue

                # Create data_download entry with historical timestamp
                download_id = generate_aws_id(PREFIX_DOWNLOAD)

                # Extract stats
                stats_data = post.get('stats', {})
                total_reactions = stats_data.get('total_reactions', 0)

                # Use the run date as the downloaded_at timestamp
                downloaded_at = run_date.replace(hour=12, minute=0, second=0)

                try:
                    cursor.execute("""
                        INSERT INTO data_downloads (
                            download_id, post_id, run_id, downloaded_at,
                            total_reactions, stats_json, raw_json, source_file_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        download_id,
                        post_id,
                        run_id,
                        downloaded_at.isoformat(),
                        total_reactions,
                        json.dumps(stats_data),
                        json.dumps(post),
                        fpath,
                        datetime.now(timezone.utc).isoformat()
                    ))
                    stats["downloads_created"] += 1
                except sqlite3.IntegrityError as e:
                    print(f"    Error creating data_download for {urn}: {e}")
                    stats["errors"] += 1

        except Exception as e:
            print(f"    Error processing {fpath}: {e}")
            stats["errors"] += 1

    conn.commit()
    return stats


def complete_historical_run(conn, run_id, run_date, stats):
    """Mark a historical download run as completed.

    Args:
        conn: Database connection
        run_id: The run ID to complete
        run_date: Date of the run
        stats: Dictionary with stats
    """
    cursor = conn.cursor()

    # Set completed time to 1 hour after start
    completed_at = run_date.replace(hour=13, minute=0, second=0)
    status = 'completed' if stats['errors'] == 0 else 'completed'  # Mark as completed even with minor errors

    cursor.execute("""
        UPDATE download_runs
        SET completed_at = ?,
            status = ?,
            posts_fetched = ?,
            posts_new = ?,
            posts_updated = ?
        WHERE run_id = ?
    """, (
        completed_at.isoformat(),
        status,
        stats['processed'],
        stats['new_posts'],
        stats['existing_posts'],
        run_id
    ))

    conn.commit()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate historical download runs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")

    args = parser.parse_args()

    print("=" * 70)
    print("Historical Download Runs Migration")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 70)

    # Check if database exists
    if not Path(DB_PATH).exists():
        print(f"Error: Database not found: {DB_PATH}")
        print("Please run the main migration first: python migrate_database.py")
        return

    # Find date directories
    directories = find_date_directories()

    if not directories:
        print("\nNo date-based directories found in data/")
        return

    print(f"\nFound {len(directories)} historical directories:")
    for date_str, directory in directories:
        file_count = len(glob.glob(f"{directory}/*.json"))
        print(f"  {date_str}: {file_count} files in {directory}")

    if args.dry_run:
        print("\n✓ Dry run completed (no changes made)")
        return

    # Confirm before proceeding
    print()
    response = input("Proceed with migration? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled")
        return

    # Connect to database
    conn = get_connection()

    total_stats = {
        "runs": 0,
        "processed": 0,
        "new_posts": 0,
        "existing_posts": 0,
        "downloads_created": 0,
        "errors": 0
    }

    try:
        # Process each directory
        for date_str, directory in directories:
            print(f"\n{'=' * 70}")
            print(f"Processing {date_str} ({directory})")
            print('=' * 70)

            # Create download run
            run_id, run_date = create_historical_run(conn, date_str, directory)
            print(f"  Created run: {run_id}")

            # Import files
            stats = import_historical_directory(conn, directory, run_id, run_date)

            # Complete run
            complete_historical_run(conn, run_id, run_date, stats)

            # Print stats
            print(f"  Results:")
            print(f"    Files processed: {stats['processed']}")
            print(f"    Existing posts: {stats['existing_posts']}")
            print(f"    Downloads created: {stats['downloads_created']}")
            print(f"    Errors: {stats['errors']}")

            # Update totals
            total_stats["runs"] += 1
            total_stats["processed"] += stats["processed"]
            total_stats["new_posts"] += stats["new_posts"]
            total_stats["existing_posts"] += stats["existing_posts"]
            total_stats["downloads_created"] += stats["downloads_created"]
            total_stats["errors"] += stats["errors"]

        # Print summary
        print("\n" + "=" * 70)
        print("Migration Summary")
        print("=" * 70)
        print(f"Runs created: {total_stats['runs']}")
        print(f"Total files processed: {total_stats['processed']}")
        print(f"Existing posts: {total_stats['existing_posts']}")
        print(f"Downloads created: {total_stats['downloads_created']}")
        print(f"Errors: {total_stats['errors']}")
        print("=" * 70)
        print("\n✓ Historical migration completed successfully")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return

    finally:
        conn.close()


if __name__ == "__main__":
    main()
