-- ============================================ 
-- Update View: v_main_post_view
-- ============================================ 
-- Purpose: Add 'platform' and 'urn' columns to the main post view
-- to support filtering by platform (e.g., YouTube) and accessing unique IDs.
-- ============================================ 

DROP VIEW IF EXISTS v_main_post_view;

CREATE VIEW v_main_post_view AS
SELECT
    p.post_id,
    p.platform,  -- Added platform
    p.urn,       -- Added urn
    to_char(to_timestamp((p.posted_at_timestamp / 1000.0)), 'YYYY-MM-DD HH24:MI:SS'::text) AS posted_at_formatted,
    p.author_username,
    substring(p.text_content, 1, 50) AS text_preview,
    CASE
        WHEN (p.raw_json::jsonb -> 'media' ->> 'type') = 'images' AND jsonb_array_length(p.raw_json::jsonb -> 'media' -> 'images') > 1 THEN '📷(' || jsonb_array_length(p.raw_json::jsonb -> 'media' -> 'images') || ')'
        WHEN (p.raw_json::jsonb -> 'media' ->> 'type') IN ('image', 'images', 'video') THEN '📷'
        -- Also check for platform specific media logic if needed, but the above JSON check usually covers it
        -- if the fetcher populates raw_json correctly. For YouTube fetcher we populate raw_json.
        ELSE ''
    END AS media_indicator,
    CASE
        WHEN aq.action_types IS NOT NULL THEN aq.action_types
        ELSE ''
    END AS marked_indicator,
    p.first_seen_at,
    p.raw_json
FROM
    posts p
LEFT JOIN (
    SELECT
        post_id,
        string_agg(action_type, '') AS action_types
    FROM
        action_queue
    GROUP BY
        post_id
) aq ON p.post_id = aq.post_id
ORDER BY
    p.posted_at_timestamp DESC;

COMMENT ON VIEW v_main_post_view IS 'Main view for TUI with formatted dates, media indicators, and now platform/urn.';