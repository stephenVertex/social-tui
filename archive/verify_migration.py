#!/usr/bin/env python3
"""Verify data migration completeness and integrity."""

import sqlite3
from supabase_client import get_supabase_client


def verify_migration():
    """Verify all data migrated correctly from SQLite to Supabase."""
    print("="*60)
    print("VERIFYING DATA MIGRATION")
    print("="*60)

    # Connect to both databases
    sqlite_conn = sqlite3.connect("data/posts_v2.db")
    supabase = get_supabase_client()

    tables_to_verify = [
        'posts',
        'profiles',
        'tags',
        'download_runs',
        'profile_tags',
        'post_tags',
        'data_downloads',
        'action_queue',
        'post_media',
    ]

    all_passed = True

    for table in tables_to_verify:
        # Count rows in SQLite
        cursor = sqlite_conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = cursor.fetchone()[0]

        # Count rows in Supabase
        result = supabase.table(table).select('*', count='exact').execute()
        supabase_count = result.count if result.count is not None else 0

        # Compare
        status = "✓" if sqlite_count == supabase_count else "✗"
        if sqlite_count != supabase_count:
            all_passed = False

        print(f"{status} {table:<20} SQLite: {sqlite_count:<6} Supabase: {supabase_count:<6}")

    sqlite_conn.close()

    print()
    print("="*60)

    if all_passed:
        print("✓ ALL TABLES VERIFIED SUCCESSFULLY!")
        print("  Row counts match between SQLite and Supabase")
    else:
        print("✗ VERIFICATION FAILED")
        print("  Some tables have mismatched row counts")

    print("="*60)

    # Additional checks
    print("\nAdditional Verification:")

    # Check foreign key relationships
    print("\n1. Checking foreign key relationships...")

    # Check profile_tags references
    result = supabase.table('profile_tags').select('profile_id, tag_id').execute()
    profile_tags = result.data

    orphaned = 0
    for pt in profile_tags:
        # Check profile exists
        p_result = supabase.table('profiles').select('profile_id').eq('profile_id', pt['profile_id']).execute()
        if not p_result.data:
            orphaned += 1
            print(f"  ✗ Orphaned profile_tag: profile {pt['profile_id']} doesn't exist")

        # Check tag exists
        t_result = supabase.table('tags').select('tag_id').eq('tag_id', pt['tag_id']).execute()
        if not t_result.data:
            orphaned += 1
            print(f"  ✗ Orphaned profile_tag: tag {pt['tag_id']} doesn't exist")

    if orphaned == 0:
        print("  ✓ All profile_tags have valid foreign keys")

    # Check data_downloads references
    print("\n2. Checking data_downloads foreign keys...")
    result = supabase.table('data_downloads').select('post_id, run_id').limit(100).execute()
    downloads = result.data

    orphaned_downloads = 0
    for dl in downloads:
        # Check post exists
        p_result = supabase.table('posts').select('post_id').eq('post_id', dl['post_id']).execute()
        if not p_result.data:
            orphaned_downloads += 1

        # Check run exists
        r_result = supabase.table('download_runs').select('run_id').eq('run_id', dl['run_id']).execute()
        if not r_result.data:
            orphaned_downloads += 1

    if orphaned_downloads == 0:
        print(f"  ✓ Checked {len(downloads)} data_downloads - all have valid foreign keys")
    else:
        print(f"  ✗ Found {orphaned_downloads} orphaned data_download records")

    # Sample data check
    print("\n3. Checking sample data integrity...")

    # Get a random post from SQLite
    sqlite_conn = sqlite3.connect("data/posts_v2.db")
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM posts LIMIT 1")
    sqlite_post = dict(cursor.fetchone())

    # Get same post from Supabase
    result = supabase.table('posts').select('*').eq('post_id', sqlite_post['post_id']).execute()
    if result.data:
        supabase_post = result.data[0]

        # Compare key fields
        fields_match = (
            sqlite_post['urn'] == supabase_post['urn'] and
            sqlite_post['author_username'] == supabase_post['author_username'] and
            bool(sqlite_post['is_read']) == supabase_post['is_read'] and
            bool(sqlite_post['is_marked']) == supabase_post['is_marked']
        )

        if fields_match:
            print(f"  ✓ Sample post data matches (post_id: {sqlite_post['post_id']})")
        else:
            print(f"  ✗ Sample post data mismatch")
    else:
        print(f"  ✗ Post {sqlite_post['post_id']} not found in Supabase")

    sqlite_conn.close()

    print("\n" + "="*60)
    print("VERIFICATION COMPLETE")
    print("="*60)


if __name__ == "__main__":
    verify_migration()
