-- Migration: 014_health_metrics_daily_view.sql
-- Purpose: Create daily aggregation view from health_metrics for insights engine
-- This replaces direct queries to user_health_data table

-- First, update the metric_type constraint to allow new sleep metrics
-- (Run this only if the constraint exists)
DO $$
BEGIN
  ALTER TABLE health_metrics DROP CONSTRAINT IF EXISTS health_metrics_metric_type_check;

  ALTER TABLE health_metrics ADD CONSTRAINT health_metrics_metric_type_check CHECK (
    metric_type IN (
      'steps', 'sleep_duration', 'sleep_start', 'sleep_end',
      'active_energy', 'heart_rate', 'resting_heart_rate',
      'distance', 'heart_rate_variability',
      'water_intake', 'mood', 'stress_level',
      'nutrition_calories', 'nutrition_protein', 'nutrition_carbs', 'nutrition_fat'
    )
  );
EXCEPTION
  WHEN undefined_object THEN
    -- Constraint doesn't exist, that's fine
    NULL;
END $$;

-- Daily aggregation view (replaces user_health_data queries)
CREATE OR REPLACE VIEW health_metrics_daily AS
SELECT
  user_id,
  DATE(recorded_at) as date,

  -- Sleep metrics
  SUM(CASE WHEN metric_type = 'sleep_duration' THEN value ELSE 0 END) as sleep_duration_hours,
  -- Bedtime: earliest sleep_start of the night (stored as decimal hours, e.g., 22.5 = 10:30 PM)
  MIN(CASE WHEN metric_type = 'sleep_start' THEN value END) as sleep_start_hour,
  -- Wake time: latest sleep_end of the morning (stored as decimal hours, e.g., 7.25 = 7:15 AM)
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

  -- Data completeness: percentage of core fields present (sleep + steps + heart rate)
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
GROUP BY user_id, DATE(recorded_at);

-- Index to optimize the view queries (aggregation by user + date)
CREATE INDEX IF NOT EXISTS idx_health_metrics_user_date
ON health_metrics(user_id, DATE(recorded_at));

-- Index for sleep metrics queries
CREATE INDEX IF NOT EXISTS idx_health_metrics_sleep
ON health_metrics(user_id, metric_type, recorded_at)
WHERE metric_type IN ('sleep_duration', 'sleep_start', 'sleep_end');

COMMENT ON VIEW health_metrics_daily IS 'Daily aggregation of health_metrics for insights engine. Includes sleep times, activity, and heart rate data.';
