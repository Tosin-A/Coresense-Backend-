-- Migration: 011_health_data_schema.sql
-- Purpose: Add health data snapshots + pattern analysis tables for health-first insights

-- Daily health data snapshots (aggregated by date)
CREATE TABLE IF NOT EXISTS user_health_data (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  date DATE NOT NULL,

  -- Sleep
  sleep_duration_hours DECIMAL(4,2),
  sleep_start_time TIME,
  sleep_end_time TIME,
  sleep_quality_score INT,

  -- Activity
  steps INT,
  active_minutes INT,
  exercise_minutes INT,
  sedentary_minutes INT,

  -- Energy/Activity by time of day
  hourly_activity JSONB,

  -- Heart rate
  resting_heart_rate INT,
  avg_heart_rate INT,

  -- Metadata
  data_completeness DECIMAL(3,2),
  synced_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_health_data_user_date
  ON user_health_data(user_id, date DESC);

-- Health pattern analysis results
CREATE TABLE IF NOT EXISTS user_health_patterns (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  pattern_type TEXT NOT NULL,
  confidence_score DECIMAL(3,2),
  pattern_data JSONB NOT NULL,
  insight_generated BOOLEAN DEFAULT false,
  calculated_at TIMESTAMPTZ DEFAULT NOW(),
  valid_until TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),

  UNIQUE(user_id, pattern_type)
);

-- Update insights table to support health-based insights
ALTER TABLE insights
ADD COLUMN IF NOT EXISTS source_data_type TEXT DEFAULT 'commitment_history'
  CHECK (source_data_type IN ('commitment_history', 'health_data', 'hybrid'));

COMMENT ON TABLE user_health_data IS 'Daily health data snapshots for sleep/activity analysis';
COMMENT ON TABLE user_health_patterns IS 'Derived health patterns for insight generation';
