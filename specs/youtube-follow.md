# Specification: YouTube Channel Monitoring

## 1. Objective

To extend the `social-tui` application to monitor specified YouTube channels for new videos. The new videos will be treated as "posts" and integrated into the existing TUI for viewing, filtering, and management, similar to the current LinkedIn functionality.

## 2. Data Model Integration

The existing Supabase schema is well-suited for this feature. No immediate schema changes (DDL) are required.

### `posts` table

-   **`post_id`**: A unique ID generated for the new video post.
-   **`urn`**: The YouTube video ID (e.g., `dQw4w9WgXcQ`). This will be the unique identifier for a video.
-   **`platform`**: Set to `'youtube'`.
-   **`posted_at_timestamp`**: The video's publication timestamp (Unix timestamp).
-   **`author_username`**: The YouTube channel's custom handle or ID.
-   **`text_content`**: The full description of the YouTube video. The video title will be prepended to the description.
-   **`url`**: The full URL to the YouTube video (e.g., `https://www.youtube.com/watch?v=dQw4w9WgXcQ`).
-   **`raw_json`**: The complete JSON object for the video, as returned by the data source (e.g., YouTube API).

### `post_media` table

A new record will be created in this table for each video, linked by `post_id`.

-   **`media_type`**: Set to `'video'`.
-   **`media_url`**: The YouTube video URL.
-   **`local_file_path`**: Can store the path to a downloaded thumbnail.
-   Other fields like `width`, `height` can be populated with thumbnail dimensions.

### `profiles` table

This table will be used to manage the list of channels to be monitored.

-   **`username`**: The YouTube channel's handle (e.g., `@Supabase`).
-   **`platform`**: Set to `'youtube'`.
-   **`is_active`**: Used to enable or disable monitoring for a specific channel.

## 3. System Components

### 3.1. Data Fetcher (`youtube_fetcher.py`)

A new Python script responsible for fetching video data.

-   **Input**: Reads the list of active YouTube channels from the `profiles` table (`platform = 'youtube'` and `is_active = true`).
-   **Logic**:
    -   For each channel, it will fetch the most recent videos (e.g., last 10).
    -   It will check the `posts` table (by `urn`) to see if a video has already been ingested.
    -   If a video is new, it will create a new record in the `posts` table and a corresponding record in the `post_media` table.
-   **Data Source**: A library such as `yt-dlp` (used as a Python library or via subprocess) can be used to retrieve video metadata without requiring a YouTube API key. This avoids API key management and quotas.
-   **Execution**: This script will be run periodically (e.g., via a cron job or manually).

### 3.2. Interactive Viewer (`interactive_youtube.py`)

A new TUI, adapted from `interactive_posts.py`.

-   **Data Loading**: It will query the `v_main_post_view` (or directly from the `posts` table) but will filter for `platform = 'youtube'`.
-   **Display**:
    -   The main table will show video title, channel name, publication date, etc.
    -   The detail view will show the full video description, link, and thumbnail.
-   **Functionality**:
    -   The "View Image" (`i`) key will display the video thumbnail using the Kitty graphics protocol.
    -   The "Open URL" (`o`) key will open the video in the default web browser.
    -   All marking and saving functionality will be preserved.

## 4. Workflow

1.  A user adds a new YouTube channel to the `profiles` table using a utility script or directly in Supabase.
2.  The `youtube_fetcher.py` script is executed.
3.  The script fetches recent videos from the new channel.
4.  New videos are identified and saved as new records in the `posts` and `post_media` tables.
5.  The user launches the `interactive_youtube.py` TUI.
6.  The TUI loads and displays only the posts where `platform = 'youtube'`.
7.  The user can browse, view details, and open videos in their browser.
