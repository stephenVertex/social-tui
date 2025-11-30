"""
Supabase client configuration and connection management.
"""
import os
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

# Supabase configuration
SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY: Optional[str] = os.getenv("SUPABASE_API_KEY")

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get or create a Supabase client instance.

    Returns:
        Client: Configured Supabase client

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_API_KEY are not set
    """
    global _supabase_client

    if _supabase_client is None:
        if not SUPABASE_URL:
            raise ValueError("SUPABASE_URL environment variable is not set")
        if not SUPABASE_API_KEY:
            raise ValueError("SUPABASE_API_KEY environment variable is not set")

        _supabase_client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

    return _supabase_client


def test_connection() -> bool:
    """
    Test the Supabase connection by attempting to query the database.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        client = get_supabase_client()
        # Try to execute a simple query to test connection
        # This will fail gracefully if no tables exist yet
        result = client.table('_supabase_test').select('*').limit(1).execute()
        return True
    except Exception as e:
        print(f"Connection test info: {e}")
        # Even if the table doesn't exist, if we get this far, connection works
        return "relation" in str(e).lower() or "table" in str(e).lower()


if __name__ == "__main__":
    # Test the connection when run directly
    print("Testing Supabase connection...")
    print(f"URL: {SUPABASE_URL}")
    print(f"API Key: {'*' * 20 if SUPABASE_API_KEY else 'Not set'}")

    try:
        client = get_supabase_client()
        print("✓ Supabase client created successfully")

        if test_connection():
            print("✓ Connection to Supabase verified")
        else:
            print("✗ Connection test failed")
    except Exception as e:
        print(f"✗ Error: {e}")
