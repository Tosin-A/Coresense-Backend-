-- Migration: 016_deprecate_user_health_data.sql
-- Purpose: Mark user_health_data table as deprecated
-- Run this after verifying data parity with migration 015

-- Add deprecation comment
COMMENT ON TABLE user_health_data IS 'DEPRECATED (2025-01): Use health_metrics_daily view instead. This table is no longer written to. Kept for historical reference. Will be dropped after 30 days.';

-- Note: The table is intentionally NOT dropped yet to allow for rollback if needed
-- After 30 days with no issues, run the following to drop the table:
/*
DROP TABLE IF EXISTS user_health_data;
*/

-- Verification query to ensure the view works correctly
-- Run this to compare old table vs new view data:
/*
SELECT
    'user_health_data' as source,
    COUNT(*) as row_count,
    COUNT(DISTINCT user_id) as unique_users
FROM user_health_data
UNION ALL
SELECT
    'health_metrics_daily' as source,
    COUNT(*) as row_count,
    COUNT(DISTINCT user_id) as unique_users
FROM health_metrics_daily;
*/
