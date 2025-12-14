# Substack Feed Reader

> **Status: Integrated**
> This functionality has been fully integrated into the main application. You can now add Substack profiles via the UI and fetch articles using `substack_fetcher.py`.

## Overview
This utility connects to Substack RSS feeds for configured profiles and retrieves the latest articles. It parses the feeds to extract article titles, links, and publication dates, storing them in the Supabase `posts` table.

## Files Involved
*   `substack_fetcher.py`: The main Python script that fetches and stores articles for all active Substack profiles.
*   `trilogy_substack_feed_reader.py`: (Deprecated) Original single-feed prototype.

## Dependencies
*   `feedparser`: Used for parsing the RSS feed data.

## Usage

### 1. Add Profiles
Use the main application UI (`main.py`) to add Substack profiles.
*   Go to Profile Management.
*   Press 'a' to add a profile.
*   Enter the Substack URL (e.g., `trilogyai.substack.com`). The system will automatically detect the platform.

### 2. Fetch Articles
To fetch articles for all active Substack profiles, run:

```bash
uv run python3 substack_fetcher.py
```

This will:
1.  Fetch all active profiles with `platform='substack'`.
2.  Parse their RSS feeds (typically the latest ~20 posts).
3.  Upsert articles into the `posts` table.

### 3. Fetch Analytics & Backfill
To fetch likes, comments, and older posts (up to 50 recent), run:

```bash
uv run python3 substack_analytics_fetcher.py
```

This will:
1.  Iterate through the last 50 posts for each profile.
2.  Update `likes_count` and `comments_count`.
3.  **Backfill** any posts that are missing from the database (e.g., older than what the RSS feed provides).
4.  Run slowly (1 request/second) to respect rate limits.

## Data Structure
Articles are stored in the `posts` table with:
*   `platform`: 'substack'
*   `urn`: `substack:<username>:<article_slug>`
*   `text_content`: Article summary/description.
*   `url`: Link to the full article.
*   `likes_count`: Number of likes/hearts.
*   `comments_count`: Number of comments.

