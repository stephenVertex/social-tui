#!/usr/bin/env python3
"""
Display LinkedIn posts from JSON files in a formatted table.
"""

import json
import glob
from pathlib import Path
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.table import Table


def load_posts(data_dir: str) -> list:
    """Load all posts from JSON files in the specified directory."""
    posts = []
    json_files = glob.glob(f"{data_dir}/*.json")

    for file_path in json_files:
        with open(file_path, 'r') as f:
            data = json.load(f)
            # Each file contains an array of posts
            if isinstance(data, list):
                posts.extend(data)

    return posts


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except:
        return datetime.min


def main():
    # Load all posts
    data_dir = "data/20251125/linkedin"
    posts = load_posts(data_dir)

    # Calculate date threshold (30 days ago)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # Extract relevant data and filter by date
    post_data = []
    for post in posts:
        date_str = post.get("posted_at", {}).get("date", "")
        username = post.get("author", {}).get("username", "")
        text = post.get("text", "")

        # Parse date
        datetime_obj = parse_date(date_str)

        # Skip posts older than 30 days
        if datetime_obj < thirty_days_ago:
            continue

        # Truncate text to first 50 characters
        text_preview = text[:50] if text else ""

        post_data.append({
            "date": date_str,
            "username": username,
            "text": text_preview,
            "datetime_obj": datetime_obj
        })

    # Sort by date, newest first
    post_data.sort(key=lambda x: x["datetime_obj"], reverse=True)

    # Create and display table
    console = Console()
    table = Table(title=f"LinkedIn Posts - Last 30 Days ({len(post_data)} total)")

    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Username", style="magenta")
    table.add_column("Text (first 50 chars)", style="white")

    for post in post_data:
        table.add_row(
            post["date"],
            post["username"],
            post["text"]
        )

    console.print(table)


if __name__ == "__main__":
    main()
