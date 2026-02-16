-- Migration: 021_fix_health_metrics_view.sql
-- Purpose: Fix missing sleep_start_time and sleep_end_time columns in health_metrics_daily view
-- Run this on Supabase to fix the "column does not exist" error

DROP VIEW IF EXISTS health_metrics_daily;

CREATE VIEW health_metrics_daily AS
SELECT
    user_id,
    recorded_date AS date,
    -- Sleep metrics
    SUM(CASE WHEN metric_type = 'sleep_duration' THEN value ELSE 0 END) as sleep_duration_hours,
    MIN(CASE WHEN metric_type = 'sleep_start' THEN value END) as sleep_start_hour,
    MAX(CASE WHEN metric_type = 'sleep_end' THEN value END) as sleep_end_hour,
    -- Convert to TIME format for display
    CASE
        WHEN MIN(CASE WHEN metric_type = 'sleep_start' THEN value END) IS NOT NULL
        THEN MAKE_TIME(
            FLOOR(MIN(CASE WHEN metric_type = 'sleep_start' THEN value END))::INT % 24,
            ((MIN(CASE WHEN metric_type = 'sleep_start' THEN value END) % 1) * 60)::INT,
            0
        )
    END as sleep_start_time,
    CASE
        WHEN MAX(CASE WHEN metric_type = 'sleep_end' THEN value END) IS NOT NULL
        THEN MAKE_TIME(
            FLOOR(MAX(CASE WHEN metric_type = 'sleep_end' THEN value END))::INT % 24,
            ((MAX(CASE WHEN metric_type = 'sleep_end' THEN value END) % 1) * 60)::INT,
            0
        )
    END as sleep_end_time,
    -- Activity metrics
    SUM(CASE WHEN metric_type = 'steps' THEN value ELSE 0 END)::INT as steps,
    SUM(CASE WHEN metric_type = 'active_energy' THEN value ELSE 0 END) as active_energy,
    SUM(CASE WHEN metric_type = 'distance' THEN value ELSE 0 END) as distance_km,
    -- Heart rate metrics
    AVG(CASE WHEN metric_type = 'heart_rate' THEN value END)::INT as avg_heart_rate,
    MIN(CASE WHEN metric_type = 'resting_heart_rate' THEN value END)::INT as resting_heart_rate,
    -- Data completeness
    ROUND(
        ((CASE WHEN SUM(CASE WHEN metric_type = 'sleep_duration' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END) +
         (CASE WHEN SUM(CASE WHEN metric_type = 'steps' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END) +
         (CASE WHEN SUM(CASE WHEN metric_type = 'heart_rate' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END)) / 3.0,
        2
    ) as data_completeness,
    -- Metadata
    COUNT(DISTINCT metric_type) as metrics_count,
    MAX(recorded_at) as last_sync_at
FROM health_metrics
GROUP BY user_id, recorded_date;

COMMENT ON VIEW health_metrics_daily IS 'Daily aggregation of health_metrics for insights engine. Includes sleep times (as TIME), activity, and heart rate data.';

-- Verify the view was created correctly
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'health_metrics_daily'
ORDER BY ordinal_position;
