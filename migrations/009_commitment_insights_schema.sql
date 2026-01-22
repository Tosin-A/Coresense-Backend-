-- Migration: 009_commitment_insights_schema.sql
-- Purpose: Add commitment tracking columns and create pattern data tables for AI insights

-- Add commitment tracking columns
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS time_of_day TEXT;
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS day_of_week INTEGER;

-- User pattern data (aggregated stats)
CREATE TABLE IF NOT EXISTS user_pattern_data (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  pattern_type TEXT NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  aggregated_data JSONB DEFAULT '{}',
  sample_size INTEGER DEFAULT 0,
  confidence_score FLOAT DEFAULT 0.0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, pattern_type, period_start)
);

-- Create index for efficient user lookups
CREATE INDEX IF NOT EXISTS idx_user_pattern_data_user ON user_pattern_data(user_id, pattern_type, period_start DESC);

-- Enhance insights table with new columns
ALTER TABLE insights ADD COLUMN IF NOT EXISTS insight_category TEXT DEFAULT 'behavioral';
ALTER TABLE insights ADD COLUMN IF NOT EXISTS coach_commentary TEXT;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS evidence_data JSONB DEFAULT '{}';
ALTER TABLE insights ADD COLUMN IF NOT EXISTS is_new BOOLEAN DEFAULT true;

-- Insight interactions table for tracking user engagement
CREATE TABLE IF NOT EXISTS insight_interactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  insight_id UUID REFERENCES insights(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  interaction_type TEXT NOT NULL, -- 'helpful', 'not_helpful', 'dismissed', 'viewed'
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for efficient user interaction lookups
CREATE INDEX IF NOT EXISTS idx_insight_interactions_user ON insight_interactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insight_interactions_insight ON insight_interactions(insight_id, interaction_type);

-- Add comment for documentation
COMMENT ON TABLE user_pattern_data IS 'Stores aggregated user behavior patterns for insight generation';
COMMENT ON TABLE insight_interactions IS 'Tracks user engagement with insights for feedback loop';
