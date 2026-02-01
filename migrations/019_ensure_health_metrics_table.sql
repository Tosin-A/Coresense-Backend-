-- Migration: 019_ensure_health_metrics_table.sql
-- Purpose: Ensure health_metrics table exists with correct schema for HealthKit sync
-- This consolidates all health_metrics requirements

-- ============================================
-- Create health_metrics table if not exists
-- ============================================
CREATE TABLE IF NOT EXISTS health_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    metric_type TEXT NOT NULL,
    value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    source TEXT DEFAULT 'healthkit',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Add indexes for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_health_metrics_user_id
    ON health_metrics(user_id);

CREATE INDEX IF NOT EXISTS idx_health_metrics_user_date
    ON health_metrics(user_id, DATE(recorded_at));

CREATE INDEX IF NOT EXISTS idx_health_metrics_lookup
    ON health_metrics(user_id, metric_type, recorded_at DESC);

-- ============================================
-- Create unique constraint for upserts
-- ============================================
CREATE UNIQUE INDEX IF NOT EXISTS health_metrics_unique
    ON health_metrics(user_id, metric_type, recorded_at);

-- ============================================
-- Add check constraint for metric types
-- ============================================
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
    WHEN undefined_object THEN NULL;
END $$;

-- ============================================
-- Row Level Security
-- ============================================
ALTER TABLE health_metrics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own health metrics" ON health_metrics;
CREATE POLICY "Users manage own health metrics" ON health_metrics
    FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service role full access to health_metrics" ON health_metrics;
CREATE POLICY "Service role full access to health_metrics" ON health_metrics
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

-- ============================================
-- Recreate the daily aggregation view
-- ============================================
CREATE OR REPLACE VIEW health_metrics_daily AS
SELECT
    user_id,
    DATE(recorded_at) as date,
    -- Sleep metrics
    SUM(CASE WHEN metric_type = 'sleep_duration' THEN value ELSE 0 END) as sleep_duration_hours,
    MIN(CASE WHEN metric_type = 'sleep_start' THEN value END) as sleep_start_hour,
    MAX(CASE WHEN metric_type = 'sleep_end' THEN value END) as sleep_end_hour,
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
GROUP BY user_id, DATE(recorded_at);

COMMENT ON VIEW health_metrics_daily IS 'Daily aggregation of health_metrics for insights engine';

-- Done
SELECT 'health_metrics table and view ready' as status;
