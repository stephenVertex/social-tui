-- Create view to consolidate profile data, post counts, and tags
-- This replaces 3N+2 queries with a single query for the profiles screen

CREATE OR REPLACE VIEW v_profiles_with_stats AS
SELECT
    p.profile_id,
    p.username,
    p.name,
    p.platform,
    p.notes,
    p.is_active,
    p.created_at,
    p.updated_at,
    p.last_synced_at,
    -- Aggregate post count per profile
    COALESCE(post_counts.post_count, 0) as post_count,
    -- Aggregate tags as JSON array
    COALESCE(
        json_agg(
            json_build_object(
                'tag_id', t.tag_id,
                'name', t.name,
                'color', t.color,
                'description', t.description
            ) ORDER BY t.name
        ) FILTER (WHERE t.tag_id IS NOT NULL),
        '[]'::json
    ) as tags
FROM profiles p
-- Get post counts
LEFT JOIN (
    SELECT
        author_username,
        COUNT(*) as post_count
    FROM posts
    GROUP BY author_username
) post_counts ON p.username = post_counts.author_username
-- Get tags
LEFT JOIN profile_tags pt ON p.profile_id = pt.profile_id
LEFT JOIN tags t ON pt.tag_id = t.tag_id
GROUP BY
    p.profile_id,
    p.username,
    p.name,
    p.platform,
    p.notes,
    p.is_active,
    p.created_at,
    p.updated_at,
    p.last_synced_at,
    post_counts.post_count
ORDER BY p.created_at DESC;
