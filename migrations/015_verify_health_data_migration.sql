-- Migration: 015_verify_health_data_migration.sql
-- Purpose: Verify all user_health_data is represented in health_metrics before deprecation
-- Run this after deploying the health_metrics_daily view

-- Check for any user_health_data rows that don't have corresponding health_metrics
DO $$
DECLARE
    gap_count INTEGER;
    total_uhd INTEGER;
BEGIN
    -- Count total rows in user_health_data
    SELECT COUNT(*) INTO total_uhd FROM user_health_data;

    -- Count gaps: user_health_data rows without corresponding health_metrics
    SELECT COUNT(*) INTO gap_count
    FROM user_health_data uhd
    WHERE NOT EXISTS (
        SELECT 1 FROM health_metrics hm
        WHERE hm.user_id = uhd.user_id
        AND DATE(hm.recorded_at) = uhd.date
        AND hm.metric_type IN ('steps', 'sleep_duration')
    )
    AND (uhd.steps IS NOT NULL OR uhd.sleep_duration_hours IS NOT NULL);

    RAISE NOTICE 'Total user_health_data rows: %', total_uhd;
    RAISE NOTICE 'Rows without corresponding health_metrics: %', gap_count;

    IF gap_count > 0 THEN
        RAISE NOTICE 'ACTION REQUIRED: Run backfill before deprecating user_health_data';
    ELSE
        RAISE NOTICE 'All user_health_data is represented in health_metrics - safe to deprecate';
    END IF;
END $$;

-- Optional: Backfill missing data from user_health_data to health_metrics
-- Uncomment and run if gaps are found above

/*
-- Backfill steps
INSERT INTO health_metrics (user_id, metric_type, value, unit, recorded_at, source, metadata)
SELECT
    user_id,
    'steps' as metric_type,
    steps as value,
    'count' as unit,
    (date::timestamp + interval '12 hours') as recorded_at,
    'backfill_from_user_health_data' as source,
    '{}'::jsonb as metadata
FROM user_health_data
WHERE steps IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM health_metrics hm
    WHERE hm.user_id = user_health_data.user_id
    AND DATE(hm.recorded_at) = user_health_data.date
    AND hm.metric_type = 'steps'
)
ON CONFLICT (user_id, metric_type, recorded_at) DO NOTHING;

-- Backfill sleep_duration
INSERT INTO health_metrics (user_id, metric_type, value, unit, recorded_at, source, metadata)
SELECT
    user_id,
    'sleep_duration' as metric_type,
    sleep_duration_hours as value,
    'hour' as unit,
    (date::timestamp + interval '7 hours') as recorded_at,
    'backfill_from_user_health_data' as source,
    '{}'::jsonb as metadata
FROM user_health_data
WHERE sleep_duration_hours IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM health_metrics hm
    WHERE hm.user_id = user_health_data.user_id
    AND DATE(hm.recorded_at) = user_health_data.date
    AND hm.metric_type = 'sleep_duration'
)
ON CONFLICT (user_id, metric_type, recorded_at) DO NOTHING;
*/
