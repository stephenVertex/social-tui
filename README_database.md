# Database Documentation & Troubleshooting

## Schema Overview

### Core Tables

#### `posts`
- **Purpose:** Core social media posts from monitored profiles
- **Primary Key:** `post_id` (text)
- **Unique Constraint:** `urn` column
- **Key Fields:**
  - `urn`: LinkedIn activity URN (e.g., "urn:li:activity:7399332114636206080")
  - `full_urn`: Full LinkedIn URN
  - `platform`: Platform identifier (default: 'linkedin')
  - `posted_at_timestamp`: Unix timestamp of when post was published
  - `author_username`: Username of the post author
  - `text_content`: Post text content
  - `raw_json`: Complete post data as JSON
  - `first_seen_at`: When this post was first imported
  - `is_read`, `is_marked`: User interaction flags

#### `data_downloads`
- **Purpose:** Time-series snapshots of post engagement metrics
- **Primary Key:** `download_id` (text)
- **Foreign Keys:**
  - `post_id` → `posts.post_id`
  - `run_id` → `download_runs.run_id`
- **Key Fields:**
  - `downloaded_at`: Timestamp of this snapshot
  - `total_reactions`: Total reaction count at time of snapshot
  - `stats_json`: JSON string containing detailed engagement metrics
  - `raw_json`: Complete snapshot data
  - `source_file_path`: Path to source data file

#### `download_runs`
- **Purpose:** Audit trail of data scraping/download sessions
- **Primary Key:** `run_id` (text)
- **Key Fields:**
  - `started_at`, `completed_at`: Run timestamps
  - `status`: Run status (running, completed, failed)
  - `platform`: Platform for this run
  - `posts_fetched`, `posts_new`, `posts_updated`: Metrics

## Common Issues & Solutions

### Issue: Historical Tracking Data Not Displaying in UI

**Symptom:**
- UI shows "(No historical tracking data available)" message
- Database contains valid `data_downloads` records for the post
- `stats_json` column has valid JSON data

**Root Cause:**
Incorrect Supabase Python client query syntax when ordering by multiple columns.

**Location:** `interactive_posts.py:858`

**Incorrect Code:**
```python
history_result = client.table('data_downloads') \
    .select('post_id, downloaded_at, stats_json') \
    .in_('post_id', post_ids) \
    .order('post_id, downloaded_at') \  # ❌ WRONG
    .execute()
```

**Problem:**
The `.order('post_id, downloaded_at')` syntax tries to order by a single column named `"post_id, downloaded_at"` which doesn't exist. This causes the query to fail silently or return incorrectly ordered results.

**Correct Code:**
```python
history_result = client.table('data_downloads') \
    .select('post_id, downloaded_at, stats_json') \
    .in_('post_id', post_ids) \
    .order('post_id').order('downloaded_at') \  # ✅ CORRECT
    .execute()
```

**Fix:** Chain multiple `.order()` calls for multi-column sorting.

**Verification Query:**
```sql
-- Check if historical data exists for a post
SELECT
  dd.download_id,
  dd.downloaded_at,
  dd.total_reactions,
  dd.stats_json,
  LENGTH(dd.stats_json) as json_length
FROM data_downloads dd
WHERE dd.post_id = '<post_id>'
ORDER BY dd.downloaded_at ASC;

-- Example: Find post_id by URN
SELECT post_id, urn, full_urn
FROM posts
WHERE full_urn = 'urn:li:activity:7399332114636206080';
```

**Debugging Steps:**
1. Check if post exists in `posts` table
2. Query `data_downloads` table for historical snapshots
3. Verify `stats_json` contains valid JSON (not NULL, not empty string)
4. Check application logs for Supabase query errors
5. Test query syntax in Supabase dashboard or SQL client

## Supabase Python Client Gotchas

### Multi-Column Sorting
**Wrong:** `.order('col1, col2')`
**Right:** `.order('col1').order('col2')`

### JSON Column Handling
- **Storage:** JSON is stored as TEXT in `stats_json`, `raw_json` columns
- **Parsing:** Application must parse JSON strings: `json.loads(row['stats_json'])`
- **PostgreSQL:** Use `::json` cast for SQL queries: `stats_json::json`

### Query Chaining
All query methods return the query builder, allowing chaining:
```python
result = client.table('posts') \
    .select('*') \
    .eq('platform', 'linkedin') \
    .gte('posted_at_timestamp', timestamp) \
    .order('posted_at_timestamp', desc=True) \
    .limit(100) \
    .execute()
```

## Data Flow

### Import Process
1. **Scraper** → Generates JSON files in `data/YYYYMMDD/linkedin/`
2. **Import Script** → Reads JSON files, populates database
3. **`download_runs`** → Creates run record
4. **`posts`** → Inserts/updates post records (deduplication by URN)
5. **`data_downloads`** → Creates snapshot with engagement metrics

### UI Loading
1. Query `posts` table for post metadata
2. Batch query `data_downloads` for all engagement history
3. Group engagement snapshots by `post_id`
4. Attach `engagement_history` array to each post object
5. Render historical timeline in post detail view

## Performance Optimization

### N+1 Query Problem
**Avoided:** Loading engagement history uses a single batch query for all posts:
```python
# Good - Single batch query
post_ids = [row['post_id'] for row in rows]
history_result = client.table('data_downloads') \
    .select('post_id, downloaded_at, stats_json') \
    .in_('post_id', post_ids) \
    .execute()

# Bad - N queries (one per post)
for post_id in post_ids:
    history = client.table('data_downloads') \
        .select('*') \
        .eq('post_id', post_id) \
        .execute()
```

### Index Requirements
Ensure indexes exist on:
- `posts.urn` (unique)
- `posts.first_seen_at` (for "new posts" filtering)
- `data_downloads.post_id` (foreign key lookups)
- `data_downloads.downloaded_at` (time-series queries)

## Date Formats

### PostgreSQL Timestamps
- Stored with timezone: `timestamp with time zone`
- ISO 8601 format: `2025-11-30T15:51:51.799114+00:00`

### Python datetime
```python
from datetime import datetime

# Parse from database
dt = datetime.fromisoformat(row['downloaded_at'])

# Format for display
display = dt.strftime("%b %d %H:%M")  # "Nov 30 15:51"
```

## Deduplication Logic

### How Post IDs Work

The system uses **URN-based deduplication** to prevent duplicate posts:

1. **URN Extraction** (`manage_data.py:21-29`):
   ```python
   def get_post_urn(post):
       """Extract the best URN from a post object."""
       urn = post.get('full_urn')  # Prefer full_urn first
       if not urn and 'urn' in post:
           if isinstance(post['urn'], dict):
               urn = post['urn'].get('activity_urn') or post['urn'].get('ugcPost_urn')
           else:
               urn = post['urn']
       return urn
   ```

2. **Deduplication Check** (`manage_data.py:133`):
   ```python
   existing_result = client.table('posts').select('post_id').eq('urn', urn).execute()
   ```
   - Uses the `urn` column (not `full_urn`) for lookup
   - Both `urn:li:activity:*` and `urn:li:ugcPost:*` formats are supported

3. **Post ID Assignment**:
   - **First time seeing URN:** Generate new `post_id` using `generate_aws_id(PREFIX_POST)`
     - Example: `p-ed3f094d`, `p-e7e989b2`
   - **Subsequent downloads:** Reuse existing `post_id` from database

4. **Historical Tracking**:
   - **Every download** creates a new `data_downloads` record (whether post is new or duplicate)
   - This enables time-series tracking of engagement metrics
   - All downloads link to the same `post_id` via foreign key

### URN Format Differences

LinkedIn uses different URN formats for different post types:

- **Activity URN:** `urn:li:activity:7399332114636206080`
  - Used for native LinkedIn posts
- **UGC Post URN:** `urn:li:ugcPost:7398746965297041408`
  - Used for User Generated Content posts

Both are stored in both the `urn` and `full_urn` columns and are treated equally for deduplication purposes.

### Example Workflow

```
Download #1 (2025-11-25):
- URN: urn:li:ugcPost:7398746965297041408
- No existing post found
- Create post_id: p-e7e989b2
- Create data_downloads entry: dl-6ed84dd1
- Result: New post + historical snapshot

Download #2 (2025-11-28):
- URN: urn:li:ugcPost:7398746965297041408
- Existing post found: p-e7e989b2
- Reuse post_id: p-e7e989b2
- Create data_downloads entry: dl-556560bd
- Result: Duplicate post + new historical snapshot

Download #3 (2025-11-29):
- URN: urn:li:ugcPost:7398746965297041408
- Existing post found: p-e7e989b2
- Reuse post_id: p-e7e989b2
- Create data_downloads entry: dl-681d0e80
- Result: Duplicate post + new historical snapshot
```

After 3 downloads, you have:
- 1 post record (`posts` table)
- 3 historical snapshots (`data_downloads` table)

## Migration Notes

- **From SQLite to Supabase:** Completed 2025-11-29
- **Schema differences:** Supabase uses `text` for JSON columns, SQLite used `json`
- **Migration script:** Handled URN-based deduplication during import
