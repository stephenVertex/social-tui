# Data storage to a proper database

## AWS-Style Identifier Prefixes

All entities use consistent AWS-style identifiers with the format `{prefix}-{xxxxxxxx}` where `xxxxxxxx` is 8 hex characters.

| Entity | Prefix | Example | Description |
|--------|--------|---------|-------------|
| Posts | `p-` | `p-a1b2c3d4` | Individual social media posts |
| DataDownloads | `dl-` | `dl-e5f6a7b8` | Time-series metric snapshots |
| DownloadRuns | `run-` | `run-12345678` | Scraping run sessions |
| Profiles | `prf-` | `prf-9abc0def` | Social media profiles |
| Tags | `tag-` | `tag-fedcba98` | Organizational tags |
| ProfileTags | `pft-` | `pft-11223344` | Profile-tag associations |
| PostTags | `ptg-` | `ptg-55667788` | Post-tag associations |
| ActionQueue | `act-` | `act-99aabbcc` | Queued actions |
| PostMedia | `med-` | `med-ddeeff00` | Media attachments |

## Posts

Core post entity - one record per unique post.

**Status: 🟡 Partially Implemented (needs migration)**

- `post_id` (PRIMARY KEY) - System identifier: `p-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `urn` (UNIQUE, NOT NULL) - LinkedIn post URN (e.g., "7399807615448305665")
- `full_urn` (TEXT) - Full URN format (e.g., "urn:li:activity:7399807615448305665")
- `platform` (TEXT, DEFAULT 'linkedin') - Social platform ('linkedin', 'twitter', etc.)
- `posted_at_timestamp` (INTEGER, NOT NULL) - Unix timestamp when post was created
- `author_username` (TEXT) - Username of post author
- `text_content` (TEXT) - Post text content
- `post_type` (TEXT) - Type: 'regular', 'repost', 'article', etc.
- `url` (TEXT) - Link to original post
- `raw_json` (TEXT) - Complete JSON payload (denormalized)
- `first_seen_at` (TIMESTAMP) - When post was first imported into our system
- `is_read` (BOOLEAN, DEFAULT 0) - UI state: has user read this?
- `is_marked` (BOOLEAN, DEFAULT 0) - UI state: has user marked this?
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)
- `updated_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_posts_urn` ON `urn` (UNIQUE)
- `idx_posts_posted_at` ON `posted_at_timestamp`
- `idx_posts_author` ON `author_username`
- `idx_posts_platform` ON `platform`
- `idx_posts_first_seen` ON `first_seen_at`

## DataDownloads

Time-series table: tracks metrics for a post at different points in time.
Enables tracking engagement growth over time.

**Status: ❌ Not Yet Implemented**

- `download_id` (PRIMARY KEY) - Identifier: `dl-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `post_id` (FOREIGN KEY → posts.post_id, NOT NULL) - Which post this download is for
- `run_id` (FOREIGN KEY → download_runs.run_id) - Which scrape run this came from
- `downloaded_at` (TIMESTAMP, NOT NULL) - When this snapshot was taken
- `total_reactions` (INTEGER, DEFAULT 0) - Total engagement count (normalized across platforms)
- `stats_json` (TEXT) - Platform-specific stats as JSON (e.g., LinkedIn: like/support/love/etc)
- `raw_json` (TEXT) - Complete raw response from API (Apify result)
- `source_file_path` (TEXT) - Path to original JSON file
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_downloads_post_id` ON `post_id`
- `idx_downloads_run_id` ON `run_id`
- `idx_downloads_downloaded_at` ON `downloaded_at`


## DownloadRuns

Tracks each scraping run for auditing and debugging.

**Status: ❌ Not Yet Implemented**

- `run_id` (PRIMARY KEY) - Identifier: `run-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `started_at` (TIMESTAMP, NOT NULL) - When the run started
- `completed_at` (TIMESTAMP) - When the run finished (NULL if still running)
- `status` (TEXT, DEFAULT 'running') - Status: 'running', 'completed', 'failed', 'cancelled'
- `script_name` (TEXT) - Script/command executed (e.g., 'run_apify.sh')
- `platform` (TEXT, DEFAULT 'linkedin') - Which platform was scraped
- `posts_fetched` (INTEGER, DEFAULT 0) - Number of posts retrieved
- `posts_new` (INTEGER, DEFAULT 0) - Number of new posts inserted
- `posts_updated` (INTEGER, DEFAULT 0) - Number of existing posts updated
- `error_message` (TEXT) - Error details if status='failed'
- `system_info` (TEXT) - JSON with system details (hostname, user, version, etc.)
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_runs_started_at` ON `started_at`
- `idx_runs_status` ON `status`

## Profiles

Tracks social media profiles being monitored.

**Status: 🟡 Partially Implemented (needs migration to AWS-style IDs)**

- `profile_id` (PRIMARY KEY) - System identifier: `prf-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `username` (TEXT UNIQUE NOT NULL) - Platform username (e.g., LinkedIn username)
- `name` (TEXT NOT NULL) - Full display name
- `platform` (TEXT, DEFAULT 'linkedin') - Social platform
- `is_active` (BOOLEAN, DEFAULT 1) - Whether actively tracking this profile
- `notes` (TEXT) - Optional user notes about the profile
- `post_count` (INTEGER, DEFAULT 0) - Number of posts seen from this profile
- `last_synced_at` (TIMESTAMP) - Last time profile data was synced
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)
- `updated_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_profiles_username` ON `username`
- `idx_profiles_active` ON `is_active`


## Tags

Labels for organizing profiles and posts.

**Status: 🟡 Partially Implemented (needs migration to AWS-style IDs)**

- `tag_id` (PRIMARY KEY) - System identifier: `tag-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `name` (TEXT UNIQUE NOT NULL) - Tag name (lowercase, unique)
- `description` (TEXT) - Optional description of tag purpose
- `color` (TEXT, DEFAULT 'cyan') - Display color for UI
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_tags_name` ON `name`

## ProfileTags

Junction table: Many-to-many relationship between profiles and tags.

**Status: 🟡 Partially Implemented (needs migration to AWS-style IDs)**

- `profile_tag_id` (PRIMARY KEY) - System identifier: `pft-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `profile_id` (TEXT NOT NULL, FOREIGN KEY → profiles.profile_id ON DELETE CASCADE)
- `tag_id` (TEXT NOT NULL, FOREIGN KEY → tags.tag_id ON DELETE CASCADE)
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)
- **UNIQUE** constraint on `(profile_id, tag_id)`

**Indexes:**
- `idx_profile_tags_profile` ON `profile_id`
- `idx_profile_tags_tag` ON `tag_id`

## PostTags

Junction table: Many-to-many relationship between posts and tags.
Intended for AI-powered tagging of posts based on content.

**Status: ❌ Not Yet Implemented**

- `post_tag_id` (PRIMARY KEY) - System identifier: `ptg-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `post_id` (TEXT NOT NULL, FOREIGN KEY → posts.post_id ON DELETE CASCADE)
- `tag_id` (TEXT NOT NULL, FOREIGN KEY → tags.tag_id ON DELETE CASCADE)
- `confidence` (REAL) - AI confidence score (0.0 to 1.0)
- `applied_by` (TEXT, DEFAULT 'ai') - Who/what applied the tag: 'ai', 'user', 'rule'
- `system_notes` (TEXT) - Why the tag was applied (AI reasoning, rule matched, etc.)
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)
- **UNIQUE** constraint on `(post_id, tag_id)`

**Indexes:**
- `idx_post_tags_post` ON `post_id`
- `idx_post_tags_tag` ON `tag_id`
- `idx_post_tags_applied_by` ON `applied_by`


## ActionQueue

Queue of actions to be performed on posts (e.g., autoreact, comment, save).

**Status: ❌ Not Yet Implemented**

- `action_id` (PRIMARY KEY) - Identifier: `act-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `post_id` (TEXT, FOREIGN KEY → posts.post_id ON DELETE CASCADE)
- `action_type` (TEXT NOT NULL) - Action: 'autoreact', 'comment', 'save', 'bookmark', 'share', etc.
- `action_params` (TEXT) - JSON with action-specific parameters (e.g., comment text, reaction type)
- `status` (TEXT, DEFAULT 'queued') - Status: 'queued', 'in_progress', 'completed', 'failed', 'cancelled'
- `priority` (INTEGER, DEFAULT 0) - Higher number = higher priority
- `scheduled_for` (TIMESTAMP) - When to execute (NULL = ASAP)
- `executed_at` (TIMESTAMP) - When action was actually executed
- `user_notes` (TEXT) - Optional user notes explaining why action was queued
- `system_notes` (TEXT) - System-generated notes (execution logs, error details)
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)
- `updated_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_actions_post_id` ON `post_id`
- `idx_actions_status` ON `status`
- `idx_actions_scheduled` ON `scheduled_for`
- `idx_actions_priority` ON `priority DESC`


## PostMedia

Tracks media (images, videos, documents) associated with posts.
Supports AI analysis of visual content.

**Status: ❌ Not Yet Implemented**

- `media_id` (PRIMARY KEY) - System identifier: `med-{xxxxxxxx}` where xxxxxxxx is 8 hex characters
- `post_id` (TEXT NOT NULL, FOREIGN KEY → posts.post_id ON DELETE CASCADE)
- `media_type` (TEXT NOT NULL) - Type: 'image', 'video', 'document', 'carousel', etc.
- `media_url` (TEXT NOT NULL) - Original URL from social platform
- `local_file_path` (TEXT) - Path to cached file (if downloaded)
- `file_size` (INTEGER) - Size in bytes
- `mime_type` (TEXT) - MIME type (image/jpeg, video/mp4, etc.)
- `width` (INTEGER) - Image/video width in pixels
- `height` (INTEGER) - Image/video height in pixels
- `ai_analysis_status` (TEXT, DEFAULT 'pending') - Status: 'pending', 'analyzing', 'completed', 'failed'
- `ai_analysis` (TEXT) - JSON with AI analysis results (description, objects detected, text extracted, etc.)
- `ai_analyzed_at` (TIMESTAMP) - When AI analysis was completed
- `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)
- `updated_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

**Indexes:**
- `idx_media_post_id` ON `post_id`
- `idx_media_analysis_status` ON `ai_analysis_status`
- `idx_media_type` ON `media_type`

**Notes:**
- AI analysis is async and may take several seconds
- Consider a separate queue table for AI analysis jobs if needed

---

## Implementation Status Summary

| Table | Status | Notes |
|-------|--------|-------|
| Posts | 🟡 Partial | Needs migration: add AWS-style `post_id` (p-), `platform`, `post_type`, `url` |
| DataDownloads | ❌ Not Implemented | New table for time-series metrics tracking (dl- prefix) |
| DownloadRuns | ❌ Not Implemented | New table for scrape run auditing (run- prefix) |
| Profiles | 🟡 Partial | Needs migration: INTEGER `id` → TEXT `profile_id` (prf-), add `platform` field |
| Tags | 🟡 Partial | Needs migration: INTEGER `id` → TEXT `tag_id` (tag-), add `description` field |
| ProfileTags | 🟡 Partial | Needs migration: Update to AWS-style IDs (pft-), update foreign keys to TEXT |
| PostTags | ❌ Not Implemented | New junction table for AI post tagging (ptg- prefix) |
| ActionQueue | ❌ Not Implemented | New table for action queue system (act- prefix) |
| PostMedia | ❌ Not Implemented | New table for media tracking and AI analysis (med- prefix) |

## Migration Strategy

### Phase 1: Update Existing Tables
1. **Posts Table**
   - Add new columns: `post_id` (generate AWS-style IDs), `platform`, `post_type`, `url`
   - Generate `p-{xxxxxxxx}` IDs for all existing records
   - Keep `urn` as unique identifier for now (backwards compatibility)
   - Migrate `source_file` data to new `data_downloads` table

2. **Profiles Table**
   - Migrate from `id` (INTEGER) to `profile_id` (TEXT with `prf-{xxxxxxxx}` format)
   - Add `platform` column (default 'linkedin')
   - Update all `profile_tags` foreign key references

3. **Tags Table**
   - Migrate from `id` (INTEGER) to `tag_id` (TEXT with `tag-{xxxxxxxx}` format)
   - Add `description` column (nullable)
   - Update all `profile_tags` and `post_tags` foreign key references

4. **ProfileTags Table**
   - Migrate from `id` (INTEGER) to `profile_tag_id` (TEXT with `pft-{xxxxxxxx}` format)
   - Update `profile_id` and `tag_id` columns from INTEGER to TEXT
   - Regenerate with new AWS-style IDs

### Phase 2: Create New Tables
1. Create `download_runs` table
2. Create `data_downloads` table
3. Create `post_tags` junction table
4. Create `action_queue` table
5. Create `post_media` table

### Phase 3: Data Migration
1. Migrate existing post data to new structure
2. Create initial `download_runs` record for historical imports
3. Extract media from posts and populate `post_media`
4. Optionally: run AI tagging on existing posts → `post_tags`

### Phase 4: Update Application Code
1. Update `manage_data.py` to use new schema
2. Update `profile_manager.py` for new profile/tag fields
3. Update `interactive_posts.py` to support new action queue
4. Create new managers: `DownloadManager`, `MediaManager`, `ActionQueueManager`
