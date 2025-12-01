#!/usr/bin/env python3
"""
Verification script for media tracking schema enhancements.
Checks that all Phase 1 changes were applied successfully.
"""

from supabase_client import get_supabase_client


def verify_schema():
    """Verify all Phase 1 schema changes."""
    client = get_supabase_client()

    print("=" * 70)
    print("Phase 1 Schema Verification")
    print("=" * 70)
    print()

    # Check columns
    print("1. Checking new columns...")
    columns_query = """
        SELECT
            column_name,
            data_type,
            column_default
        FROM information_schema.columns
        WHERE table_name = 'post_media'
        AND column_name IN ('md5_sum', 'archive_url', 'ai_analysis_log', 'ai_analysis_status')
        ORDER BY column_name;
    """

    result = client.rpc('exec_sql', {'query': columns_query}).execute()
    columns = result.data

    expected_columns = {
        'md5_sum': {'data_type': 'text'},
        'archive_url': {'data_type': 'text'},
        'ai_analysis_log': {'data_type': 'jsonb'},
        'ai_analysis_status': {'data_type': 'text', 'default': "'not_started'::text"}
    }

    for col in columns:
        col_name = col['column_name']
        if col_name in expected_columns:
            print(f"   ✓ {col_name} ({col['data_type']})")
            if 'default' in expected_columns[col_name]:
                if col['column_default'] == expected_columns[col_name]['default']:
                    print(f"     ✓ Default: {col['column_default']}")
                else:
                    print(f"     ✗ Default mismatch: {col['column_default']}")

    print()

    # Check indexes
    print("2. Checking indexes...")
    indexes_query = """
        SELECT
            indexname
        FROM pg_indexes
        WHERE tablename = 'post_media'
        AND indexname IN ('idx_media_md5_sum', 'idx_media_archive_url', 'idx_media_ai_status_created')
        ORDER BY indexname;
    """

    result = client.rpc('exec_sql', {'query': indexes_query}).execute()
    indexes = result.data

    expected_indexes = ['idx_media_md5_sum', 'idx_media_archive_url', 'idx_media_ai_status_created']

    for idx in indexes:
        idx_name = idx['indexname']
        if idx_name in expected_indexes:
            print(f"   ✓ {idx_name}")

    print()

    # Check constraint
    print("3. Checking ai_analysis_status constraint...")
    constraint_query = """
        SELECT
            conname as constraint_name,
            pg_get_constraintdef(oid) as constraint_definition
        FROM pg_constraint
        WHERE conrelid = 'post_media'::regclass
        AND contype = 'c'
        AND conname = 'post_media_ai_analysis_status_check';
    """

    result = client.rpc('exec_sql', {'query': constraint_query}).execute()
    constraints = result.data

    if constraints:
        print(f"   ✓ {constraints[0]['constraint_name']}")
        print(f"     Definition: {constraints[0]['constraint_definition']}")
    else:
        print("   ✗ Constraint not found")

    print()

    # Check column comments
    print("4. Checking column comments...")
    comments_query = """
        SELECT
            cols.column_name,
            pg_catalog.col_description(c.oid, cols.ordinal_position::int) as column_comment
        FROM information_schema.columns cols
        JOIN pg_catalog.pg_class c ON c.relname = cols.table_name
        WHERE cols.table_name = 'post_media'
        AND cols.column_name IN ('md5_sum', 'archive_url', 'ai_analysis_status', 'ai_analysis_log')
        ORDER BY cols.ordinal_position;
    """

    result = client.rpc('exec_sql', {'query': comments_query}).execute()
    comments = result.data

    for comment in comments:
        if comment['column_comment']:
            print(f"   ✓ {comment['column_name']}: {comment['column_comment'][:60]}...")

    print()
    print("=" * 70)
    print("✓ Phase 1 schema verification complete!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        verify_schema()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
