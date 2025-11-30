"""
Schema migration script: Create PostgreSQL tables in Supabase.

This script reads the schema_postgres.sql file and executes it against
the Supabase database.

Requirements:
    - For automatic execution: Add SUPABASE_DB_URL to .env and install psycopg2
    - For manual execution: Use Supabase SQL Editor in dashboard
"""
import os
import sys
from dotenv import load_dotenv
from supabase_client import get_supabase_client

# Load environment variables
load_dotenv()

# Try to import psycopg2 for direct database access
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

def read_schema_file(filename: str = "schema_postgres.sql") -> str:
    """Read the PostgreSQL schema file."""
    with open(filename, 'r') as f:
        return f.read()


def execute_schema_direct(schema_sql: str) -> bool:
    """
    Execute schema SQL using direct database connection (requires psycopg2).
    """
    if not HAS_PSYCOPG2:
        print("✗ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return False

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("✗ SUPABASE_DB_URL not found in .env file")
        print("  Get it from: Supabase Dashboard → Settings → Database → Connection String")
        print("  Add to .env: SUPABASE_DB_URL=postgresql://...")
        return False

    try:
        print("\nConnecting to Supabase database...")
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        print("Executing schema SQL...")
        cursor.execute(schema_sql)

        conn.commit()
        cursor.close()
        conn.close()

        print("✓ Schema executed successfully!")
        return True

    except Exception as e:
        print(f"✗ Error executing schema: {e}")
        return False


def execute_schema(schema_sql: str, auto: bool = True) -> bool:
    """
    Execute the schema SQL against Supabase.

    Args:
        schema_sql: The SQL schema to execute
        auto: If True, attempt automatic execution via psycopg2

    Returns:
        bool: True if executed successfully, False otherwise
    """
    # Split the schema into individual statements for counting
    statements = [s.strip() for s in schema_sql.split(';') if s.strip() and not s.strip().startswith('--')]
    print(f"Found {len(statements)} SQL statements to execute\n")

    # Try automatic execution if requested and available
    if auto and HAS_PSYCOPG2 and os.getenv("SUPABASE_DB_URL"):
        print("Attempting automatic execution via direct database connection...")
        success = execute_schema_direct(schema_sql)
        if success:
            return True
        else:
            print("\nAutomatic execution failed. See manual instructions below.")

    # Print manual execution instructions
    print("\n" + "="*60)
    print("MANUAL SCHEMA MIGRATION")
    print("="*60)
    print("\nOption 1 - Supabase Dashboard (Easiest):")
    print("  1. Go to: https://supabase.com/dashboard/project/_/sql")
    print("  2. Copy the contents of 'schema_postgres.sql'")
    print("  3. Paste into the SQL Editor")
    print("  4. Click 'Run'")
    print("\nOption 2 - Automatic Execution:")
    print("  1. Get database URL from Supabase Settings → Database")
    print("  2. Add to .env: SUPABASE_DB_URL=postgresql://...")
    print("  3. Install: pip install psycopg2-binary")
    print("  4. Run this script again")
    print("\n" + "="*60)

    # Save a ready-to-copy version
    with open('schema_postgres_ready.sql', 'w') as f:
        f.write(schema_sql)

    print("\n✓ Created 'schema_postgres_ready.sql' for easy copying")
    print("  Copy this file's contents to Supabase SQL Editor")

    return False


def verify_schema() -> bool:
    """
    Verify that all expected tables exist in Supabase.
    """
    client = get_supabase_client()

    expected_tables = [
        'posts',
        'data_downloads',
        'download_runs',
        'profiles',
        'tags',
        'profile_tags',
        'post_tags',
        'action_queue',
        'post_media'
    ]

    print("\n" + "="*60)
    print("VERIFYING SCHEMA")
    print("="*60)

    created_tables = []
    missing_tables = []

    for table in expected_tables:
        try:
            # Try to select from the table (will fail if table doesn't exist)
            result = client.table(table).select('*').limit(1).execute()
            created_tables.append(table)
            print(f"✓ Table '{table}' exists")
        except Exception as e:
            missing_tables.append(table)
            error_msg = str(e)
            if 'PGRST204' in error_msg or 'relation' in error_msg.lower():
                print(f"✗ Table '{table}' not found")
            else:
                print(f"? Table '{table}' - unclear: {error_msg}")

    print("\n" + "="*60)
    print(f"Summary: {len(created_tables)}/{len(expected_tables)} tables exist")
    print("="*60)

    if missing_tables:
        print(f"\nMissing tables: {', '.join(missing_tables)}")
        print("Please execute the schema SQL in Supabase SQL Editor")
        return False
    else:
        print("\n✓ All tables exist! Schema migration complete.")
        return True


if __name__ == "__main__":
    import sys

    print("="*60)
    print("SUPABASE SCHEMA MIGRATION")
    print("="*60)

    # Check for verify flag
    verify_only = '--verify' in sys.argv

    if verify_only:
        print("\nVerifying existing schema...")
        verify_schema()
        sys.exit(0)

    # Read the schema file
    try:
        schema = read_schema_file()
        print(f"✓ Read schema file ({len(schema)} characters)")
    except FileNotFoundError:
        print("✗ Error: schema_postgres.sql not found")
        print("  Run this script from the project root directory")
        sys.exit(1)

    # Execute schema
    success = execute_schema(schema)

    # If execution was successful, verify
    if success:
        print("\n")
        verify_schema()
    else:
        print("\nAfter executing the schema manually, verify with:")
        print("  python migrate_schema.py --verify")
