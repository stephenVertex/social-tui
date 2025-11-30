-- ============================================
-- Supabase/PostgreSQL Schema for social-tui
-- ============================================
-- Migrated from SQLite schema
-- All tables use text-based primary keys (AWS-style: p-a1b2c3d4)
-- ============================================

-- Posts table: Core social media posts
CREATE TABLE posts (
    post_id TEXT PRIMARY KEY,
    urn TEXT UNIQUE NOT NULL,
    full_urn TEXT,
    platform TEXT DEFAULT 'linkedin',
    posted_at_timestamp BIGINT NOT NULL,
    author_username TEXT,
    text_content TEXT,
    post_type TEXT,
    url TEXT,
    raw_json TEXT,
    first_seen_at TIMESTAMPTZ,
    is_read BOOLEAN DEFAULT FALSE,
    is_marked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE posts IS 'Core social media posts from monitored profiles';
COMMENT ON COLUMN posts.posted_at_timestamp IS 'Unix timestamp of when the post was published';
COMMENT ON COLUMN posts.is_read IS 'User has marked this post as read';
COMMENT ON COLUMN posts.is_marked IS 'User has marked/starred this post for follow-up';

-- Indexes for posts table
CREATE INDEX idx_posts_urn ON posts(urn);
CREATE INDEX idx_posts_posted_at ON posts(posted_at_timestamp);
CREATE INDEX idx_posts_author ON posts(author_username);
CREATE INDEX idx_posts_platform ON posts(platform);
CREATE INDEX idx_posts_first_seen ON posts(first_seen_at);
CREATE INDEX idx_posts_is_read ON posts(is_read);
CREATE INDEX idx_posts_is_marked ON posts(is_marked);

-- Download runs table: Audit trail of scraping sessions
CREATE TABLE download_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running',
    script_name TEXT,
    platform TEXT DEFAULT 'linkedin',
    posts_fetched INTEGER DEFAULT 0,
    posts_new INTEGER DEFAULT 0,
    posts_updated INTEGER DEFAULT 0,
    error_message TEXT,
    system_info TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE download_runs IS 'Audit trail of data scraping/download sessions';

-- Indexes for download_runs table
CREATE INDEX idx_runs_started_at ON download_runs(started_at);
CREATE INDEX idx_runs_status ON download_runs(status);

-- Data downloads table: Time-series metrics snapshots
CREATE TABLE data_downloads (
    download_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL,
    run_id TEXT,
    downloaded_at TIMESTAMPTZ NOT NULL,
    total_reactions INTEGER DEFAULT 0,
    stats_json TEXT,
    raw_json TEXT,
    source_file_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES download_runs(run_id) ON DELETE SET NULL
);

COMMENT ON TABLE data_downloads IS 'Time-series snapshots of post engagement metrics';

-- Indexes for data_downloads table
CREATE INDEX idx_downloads_post_id ON data_downloads(post_id);
CREATE INDEX idx_downloads_run_id ON data_downloads(run_id);
CREATE INDEX idx_downloads_downloaded_at ON data_downloads(downloaded_at);

-- Profiles table: Monitored social media profiles
CREATE TABLE profiles (
    profile_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    platform TEXT DEFAULT 'linkedin',
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    post_count INTEGER DEFAULT 0,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE profiles IS 'Social media profiles being monitored';
COMMENT ON COLUMN profiles.is_active IS 'Whether this profile is currently being monitored';

-- Indexes for profiles table
CREATE INDEX idx_profiles_username ON profiles(username);
CREATE INDEX idx_profiles_active ON profiles(is_active);

-- Tags table: Organizational labels
CREATE TABLE tags (
    tag_id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    color TEXT DEFAULT 'cyan',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE tags IS 'Organizational tags for categorizing profiles and posts';

-- Indexes for tags table
CREATE INDEX idx_tags_name ON tags(name);

-- Profile tags junction table: Many-to-many relationship
CREATE TABLE profile_tags (
    profile_tag_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (profile_id) REFERENCES profiles(profile_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    UNIQUE(profile_id, tag_id)
);

COMMENT ON TABLE profile_tags IS 'Junction table linking profiles to tags';

-- Indexes for profile_tags table
CREATE INDEX idx_profile_tags_profile ON profile_tags(profile_id);
CREATE INDEX idx_profile_tags_tag ON profile_tags(tag_id);

-- Post tags junction table: Many-to-many with AI tagging support
CREATE TABLE post_tags (
    post_tag_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    confidence REAL,
    applied_by TEXT DEFAULT 'ai',
    system_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    UNIQUE(post_id, tag_id)
);

COMMENT ON TABLE post_tags IS 'Junction table linking posts to tags with AI confidence scores';
COMMENT ON COLUMN post_tags.confidence IS 'AI confidence score for auto-applied tags (0.0-1.0)';
COMMENT ON COLUMN post_tags.applied_by IS 'How the tag was applied: ai, user, or system';

-- Indexes for post_tags table
CREATE INDEX idx_post_tags_post ON post_tags(post_id);
CREATE INDEX idx_post_tags_tag ON post_tags(tag_id);
CREATE INDEX idx_post_tags_applied_by ON post_tags(applied_by);

-- Action queue table: Queued actions on posts
CREATE TABLE action_queue (
    action_id TEXT PRIMARY KEY,
    post_id TEXT,
    action_type TEXT NOT NULL,
    action_params TEXT,
    status TEXT DEFAULT 'queued',
    priority INTEGER DEFAULT 0,
    scheduled_for TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    user_notes TEXT,
    system_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);

COMMENT ON TABLE action_queue IS 'Queue of pending actions to perform on posts';

-- Indexes for action_queue table
CREATE INDEX idx_actions_post_id ON action_queue(post_id);
CREATE INDEX idx_actions_status ON action_queue(status);
CREATE INDEX idx_actions_scheduled ON action_queue(scheduled_for);
CREATE INDEX idx_actions_priority ON action_queue(priority DESC);

-- Post media table: Media attachments with AI analysis
CREATE TABLE post_media (
    media_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    media_url TEXT NOT NULL,
    local_file_path TEXT,
    file_size INTEGER,
    mime_type TEXT,
    width INTEGER,
    height INTEGER,
    ai_analysis_status TEXT DEFAULT 'pending',
    ai_analysis TEXT,
    ai_analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);

COMMENT ON TABLE post_media IS 'Media attachments and AI analysis metadata';
COMMENT ON COLUMN post_media.ai_analysis_status IS 'Status of AI analysis: pending, processing, completed, failed';

-- Indexes for post_media table
CREATE INDEX idx_media_post_id ON post_media(post_id);
CREATE INDEX idx_media_analysis_status ON post_media(ai_analysis_status);
CREATE INDEX idx_media_type ON post_media(media_type);
