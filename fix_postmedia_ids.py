#!/usr/bin/env python3
"""
Fix PostMedia IDs from pm- prefix to med- prefix for consistency.

This script:
1. Finds all post_media records with pm- prefix
2. Generates new med- prefix IDs
3. Updates the records in the database

Usage:
    python fix_postmedia_ids.py           # Dry run (shows what would be changed)
    python fix_postmedia_ids.py --apply   # Apply the changes
"""

import argparse
import uuid
from supabase_client import get_supabase_client


def generate_new_media_id():
    """Generate a new media ID with med- prefix."""
    return f"med-{uuid.uuid4().hex[:8]}"


def find_pm_records(client):
    """Find all post_media records with pm- prefix."""
    print("Querying database for pm- prefixed records...")

    # Fetch all records with pm- prefix
    result = client.table('post_media').select('*').like('media_id', 'pm-%').execute()

    return result.data


def update_record(client, old_id, new_id, dry_run=True):
    """Update a single record from old_id to new_id."""
    if dry_run:
        print(f"  [DRY RUN] Would update: {old_id} -> {new_id}")
        return True

    try:
        # Update the record
        client.table('post_media').update({'media_id': new_id}).eq('media_id', old_id).execute()
        print(f"  ✓ Updated: {old_id} -> {new_id}")
        return True
    except Exception as e:
        print(f"  ✗ Error updating {old_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fix PostMedia IDs from pm- to med- prefix",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fix_postmedia_ids.py           # Dry run (preview changes)
  python fix_postmedia_ids.py --apply   # Apply the changes
        """
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the changes (default is dry run)"
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("PostMedia ID Migration (pm- to med-)")
    print("=" * 70)

    if not args.apply:
        print("\n⚠ DRY RUN MODE - No changes will be made")
        print("Use --apply to actually update the database\n")
    else:
        print("\n⚠ APPLY MODE - Changes will be made to the database\n")

    # Connect to Supabase
    client = get_supabase_client()
    if not client:
        print("Failed to connect to Supabase. Check your .env file.")
        return 1

    # Find records to update
    pm_records = find_pm_records(client)

    if not pm_records:
        print("\n✓ No pm- prefixed records found. Database is already consistent!")
        return 0

    print(f"Found {len(pm_records)} record(s) with pm- prefix\n")

    # Show sample records
    print("Sample records to update:")
    for record in pm_records[:5]:
        print(f"  {record['media_id']} (post_id: {record['post_id']}, type: {record['media_type']})")
    if len(pm_records) > 5:
        print(f"  ... and {len(pm_records) - 5} more")

    print("\n" + "=" * 70)
    print("Updating Records")
    print("=" * 70 + "\n")

    # Generate mapping of old IDs to new IDs
    updates = []
    for record in pm_records:
        old_id = record['media_id']
        new_id = generate_new_media_id()
        updates.append((old_id, new_id))

    # Update records
    success_count = 0
    error_count = 0

    for old_id, new_id in updates:
        if update_record(client, old_id, new_id, dry_run=not args.apply):
            success_count += 1
        else:
            error_count += 1

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)

    if args.apply:
        print(f"  Successfully updated: {success_count}")
        if error_count > 0:
            print(f"  Errors:               {error_count}")
        print(f"\n✓ Migration completed!")
    else:
        print(f"  Records to update:    {len(updates)}")
        print(f"\n⚠ This was a dry run. Use --apply to make changes.")

    return 0


if __name__ == "__main__":
    exit(main())
