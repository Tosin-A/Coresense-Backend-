-- Migration: 010_user_metrics_schema.sql
-- Description: Create tables for personal metrics tracking (energy, mood, sleep, stress, focus)
-- Date: 2026-01-22

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Table: user_metrics
-- Tracks individual metric logs (energy, mood, sleep, etc.)
-- ============================================
CREATE TABLE IF NOT EXISTS user_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    metric_type TEXT NOT NULL CHECK (metric_type IN ('energy', 'mood', 'sleep', 'stress', 'focus')),
    value NUMERIC NOT NULL,  -- 1-5 scale for most metrics, hours for sleep
    notes TEXT,
    logged_at TIMESTAMPTZ DEFAULT NOW(),
    context JSONB,  -- e.g., {"time_of_day": "morning", "after_activity": "workout"}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_user_metrics_lookup
    ON user_metrics(user_id, metric_type, logged_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_metrics_user_date_range
    ON user_metrics(user_id, logged_at DESC);

-- ============================================
-- Table: daily_summaries
-- Aggregated daily stats for performance optimization
-- ============================================
CREATE TABLE IF NOT EXISTS daily_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    avg_energy NUMERIC,
    avg_mood NUMERIC,
    avg_stress NUMERIC,
    sleep_hours NUMERIC,
    sleep_quality NUMERIC,  -- 1-5 rating
    focus_minutes INT,
    commitments_completed INT,
    commitments_total INT,
    top_emotion TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- Index for efficient date-range queries
CREATE INDEX IF NOT EXISTS idx_daily_summaries_lookup
    ON daily_summaries(user_id, date DESC);

-- ============================================
-- Function: update_daily_summary
-- Automatically updates daily_summaries when metrics are logged
-- ============================================
CREATE OR REPLACE FUNCTION update_daily_summary()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO daily_summaries (user_id, date, avg_energy, avg_mood, avg_stress, sleep_hours)
    SELECT
        NEW.user_id,
        DATE(NEW.logged_at),
        AVG(CASE WHEN metric_type = 'energy' THEN value END),
        AVG(CASE WHEN metric_type = 'mood' THEN value END),
        AVG(CASE WHEN metric_type = 'stress' THEN value END),
        AVG(CASE WHEN metric_type = 'sleep' THEN value END)
    FROM user_metrics
    WHERE user_id = NEW.user_id AND DATE(logged_at) = DATE(NEW.logged_at)
    ON CONFLICT (user_id, date)
    DO UPDATE SET
        avg_energy = EXCLUDED.avg_energy,
        avg_mood = EXCLUDED.avg_mood,
        avg_stress = EXCLUDED.avg_stress,
        sleep_hours = EXCLUDED.sleep_hours,
        updated_at = NOW();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update daily summaries
DROP TRIGGER IF EXISTS trigger_update_daily_summary ON user_metrics;
CREATE TRIGGER trigger_update_daily_summary
    AFTER INSERT ON user_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_daily_summary();

-- ============================================
-- Row Level Security (RLS) Policies
-- ============================================

-- Enable RLS on user_metrics
ALTER TABLE user_metrics ENABLE ROW LEVEL SECURITY;

-- Users can only see their own metrics
CREATE POLICY "Users can view own metrics"
    ON user_metrics FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own metrics
CREATE POLICY "Users can insert own metrics"
    ON user_metrics FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own metrics
CREATE POLICY "Users can update own metrics"
    ON user_metrics FOR UPDATE
    USING (auth.uid() = user_id);

-- Users can delete their own metrics
CREATE POLICY "Users can delete own metrics"
    ON user_metrics FOR DELETE
    USING (auth.uid() = user_id);

-- Enable RLS on daily_summaries
ALTER TABLE daily_summaries ENABLE ROW LEVEL SECURITY;

-- Users can only see their own summaries
CREATE POLICY "Users can view own summaries"
    ON daily_summaries FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own summaries (via trigger)
CREATE POLICY "Users can insert own summaries"
    ON daily_summaries FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own summaries
CREATE POLICY "Users can update own summaries"
    ON daily_summaries FOR UPDATE
    USING (auth.uid() = user_id);

-- ============================================
-- Service role bypass for backend operations
-- ============================================

-- Allow service role to bypass RLS for user_metrics
CREATE POLICY "Service role full access to user_metrics"
    ON user_metrics FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Allow service role to bypass RLS for daily_summaries
CREATE POLICY "Service role full access to daily_summaries"
    ON daily_summaries FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- ============================================
-- Comments for documentation
-- ============================================
COMMENT ON TABLE user_metrics IS 'Individual metric logs for energy, mood, sleep, stress, and focus';
COMMENT ON TABLE daily_summaries IS 'Aggregated daily statistics computed from user_metrics';
COMMENT ON COLUMN user_metrics.value IS '1-5 scale for energy/mood/stress/focus, hours for sleep';
COMMENT ON COLUMN user_metrics.context IS 'Optional metadata like time_of_day, after_activity, etc.';
