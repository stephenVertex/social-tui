#!/usr/bin/env python3
"""
Data migration script: SQLite → Supabase

Exports all data from SQLite database and imports into Supabase,
maintaining foreign key relationships and data integrity.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
from supabase_client import get_supabase_client


# Migration order (respects foreign key dependencies)
MIGRATION_ORDER = [
    # Tier 1: No dependencies
    ('posts', 'post_id'),
    ('profiles', 'profile_id'),
    ('tags', 'tag_id'),
    ('download_runs', 'run_id'),

    # Tier 2: Depends on Tier 1
    ('profile_tags', 'profile_tag_id'),
    ('post_tags', 'post_tag_id'),
    ('data_downloads', 'download_id'),
    ('action_queue', 'queue_id'),
    ('post_media', 'media_id'),
]

# Boolean fields that need conversion (0/1 → True/False)
BOOLEAN_FIELDS = {
    'posts': ['is_read', 'is_marked'],
    'profiles': ['is_active'],
}


class DataMigrator:
    """Handles migration from SQLite to Supabase."""

    def __init__(self, sqlite_db_path: str = "data/posts_v2.db"):
        self.sqlite_db_path = sqlite_db_path
        self.supabase_client = get_supabase_client()
        self.stats = {
            'tables': {},
            'total_rows': 0,
            'total_errors': 0,
            'start_time': None,
            'end_time': None,
        }

    def export_table_from_sqlite(self, table_name: str) -> List[Dict[str, Any]]:
        """Export all rows from a SQLite table.

        Args:
            table_name: Name of table to export

        Returns:
            List of dictionaries (one per row)
        """
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        # Convert to list of dicts
        data = [dict(row) for row in rows]

        conn.close()
        return data

    def convert_boolean_fields(self, table_name: str, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert SQLite boolean fields (0/1) to Python booleans.

        Args:
            table_name: Name of table
            row: Row data dictionary

        Returns:
            Row with converted boolean fields
        """
        if table_name in BOOLEAN_FIELDS:
            for field in BOOLEAN_FIELDS[table_name]:
                if field in row and row[field] is not None:
                    row[field] = bool(row[field])
        return row

    def import_table_to_supabase(
        self,
        table_name: str,
        data: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> Tuple[int, int]:
        """Import data into Supabase table in batches.

        Args:
            table_name: Name of table to import into
            data: List of row dictionaries
            batch_size: Number of rows per batch

        Returns:
            Tuple of (successful_count, error_count)
        """
        if not data:
            return 0, 0

        successful = 0
        errors = 0

        # Process in batches
        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]

            # Convert boolean fields for entire batch
            batch = [self.convert_boolean_fields(table_name, row) for row in batch]

            try:
                # Attempt batch insert
                result = self.supabase_client.table(table_name).insert(batch).execute()
                successful += len(batch)
                print(f"  ✓ Inserted batch {i//batch_size + 1} ({len(batch)} rows)")

            except Exception as e:
                # If batch fails, try one-by-one
                print(f"  ⚠ Batch insert failed, trying row-by-row: {e}")

                for row in batch:
                    try:
                        self.supabase_client.table(table_name).insert(row).execute()
                        successful += 1
                    except Exception as row_error:
                        errors += 1
                        # Print first few errors only
                        if errors <= 5:
                            print(f"  ✗ Error inserting row: {row_error}")

        return successful, errors

    def verify_table(self, table_name: str, expected_count: int) -> bool:
        """Verify table migration was successful.

        Args:
            table_name: Name of table to verify
            expected_count: Expected number of rows

        Returns:
            True if verification passed
        """
        result = self.supabase_client.table(table_name).select('*', count='exact').execute()
        actual_count = result.count if result.count is not None else 0

        if actual_count == expected_count:
            print(f"  ✓ Verified: {actual_count} rows")
            return True
        else:
            print(f"  ✗ Mismatch: Expected {expected_count}, got {actual_count}")
            return False

    def migrate_table(self, table_name: str, primary_key: str) -> Dict[str, Any]:
        """Migrate a single table from SQLite to Supabase.

        Args:
            table_name: Name of table to migrate
            primary_key: Name of primary key column

        Returns:
            Dictionary with migration statistics
        """
        print(f"\n{'='*60}")
        print(f"Migrating table: {table_name}")
        print(f"{'='*60}")

        # Export from SQLite
        print("Exporting from SQLite...")
        data = self.export_table_from_sqlite(table_name)
        print(f"  ✓ Exported {len(data)} rows")

        if len(data) == 0:
            print("  → Table is empty, skipping")
            return {
                'table': table_name,
                'exported': 0,
                'imported': 0,
                'errors': 0,
                'verified': True
            }

        # Import to Supabase
        print("Importing to Supabase...")
        successful, errors = self.import_table_to_supabase(table_name, data)
        print(f"  ✓ Imported {successful} rows ({errors} errors)")

        # Verify
        print("Verifying...")
        verified = self.verify_table(table_name, len(data))

        return {
            'table': table_name,
            'exported': len(data),
            'imported': successful,
            'errors': errors,
            'verified': verified
        }

    def run_migration(self, tables_filter: List[str] = None) -> Dict[str, Any]:
        """Run complete migration for all tables.

        Args:
            tables_filter: Optional list of table names to migrate (if None, migrate all)

        Returns:
            Dictionary with complete migration statistics
        """
        print("\n" + "="*60)
        print("STARTING DATA MIGRATION: SQLite → Supabase")
        print("="*60)
        print(f"Source: {self.sqlite_db_path}")
        print(f"Target: Supabase")
        if tables_filter:
            print(f"Tables: {', '.join(tables_filter)}")

        self.stats['start_time'] = datetime.now()

        # Migrate each table in order
        for table_name, primary_key in MIGRATION_ORDER:
            # Skip if filtering and table not in filter
            if tables_filter and table_name not in tables_filter:
                continue

            table_stats = self.migrate_table(table_name, primary_key)
            self.stats['tables'][table_name] = table_stats
            self.stats['total_rows'] += table_stats['imported']
            self.stats['total_errors'] += table_stats['errors']

        self.stats['end_time'] = datetime.now()

        # Print summary
        self.print_summary()

        return self.stats

    def print_summary(self):
        """Print migration summary."""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Duration: {duration:.2f} seconds")
        print(f"Total rows migrated: {self.stats['total_rows']}")
        print(f"Total errors: {self.stats['total_errors']}")
        print()

        print("Table breakdown:")
        print(f"{'Table':<20} {'Exported':<12} {'Imported':<12} {'Errors':<10} {'Verified':<10}")
        print("-" * 60)

        for table_name, stats in self.stats['tables'].items():
            verified_mark = "✓" if stats['verified'] else "✗"
            print(
                f"{table_name:<20} "
                f"{stats['exported']:<12} "
                f"{stats['imported']:<12} "
                f"{stats['errors']:<10} "
                f"{verified_mark:<10}"
            )

        print()

        # Check if all tables verified
        all_verified = all(s['verified'] for s in self.stats['tables'].values())
        if all_verified and self.stats['total_errors'] == 0:
            print("✓ MIGRATION COMPLETED SUCCESSFULLY!")
        else:
            print("⚠ MIGRATION COMPLETED WITH ISSUES")
            print("  Please review errors above and verify data manually")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate data from SQLite to Supabase")
    parser.add_argument(
        "--db",
        default="data/posts_v2.db",
        help="Path to SQLite database (default: data/posts_v2.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Export data but don't import (for testing)"
    )
    parser.add_argument(
        "--tables",
        nargs='+',
        help="Migrate only specific tables (space-separated)"
    )

    args = parser.parse_args()

    # Verify SQLite database exists
    import os
    if not os.path.exists(args.db):
        print(f"Error: SQLite database not found: {args.db}")
        return 1

    # Create migrator
    migrator = DataMigrator(sqlite_db_path=args.db)

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        print("Exporting data from SQLite (will not import to Supabase)")

        for table_name, _ in MIGRATION_ORDER:
            data = migrator.export_table_from_sqlite(table_name)
            print(f"{table_name}: {len(data)} rows")

        return 0

    # Run migration
    try:
        stats = migrator.run_migration(tables_filter=args.tables)

        # Return exit code based on results
        if stats['total_errors'] > 0:
            return 1
        return 0

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
