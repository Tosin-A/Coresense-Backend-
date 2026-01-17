-- Wellness Insights Feature - Database Migrations
-- Run this in Supabase SQL Editor

-- ============================================
-- WELLNESS GOALS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS wellness_goals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  goal_type TEXT NOT NULL CHECK (goal_type IN (
    'steps', 'sleep', 'water', 'mood', 'stress', 'nutrition', 'activity'
  )),
  target_value NUMERIC NOT NULL,
  current_value NUMERIC DEFAULT 0,
  unit TEXT NOT NULL,
  period TEXT DEFAULT 'daily' CHECK (period IN ('daily', 'weekly', 'monthly')),
  start_date DATE NOT NULL,
  end_date DATE,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused', 'cancelled')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wellness_goals_user ON wellness_goals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_wellness_goals_type ON wellness_goals(user_id, goal_type, status);

-- ============================================
-- MANUAL HEALTH LOGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS manual_health_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  log_type TEXT NOT NULL CHECK (log_type IN (
    'mood', 'stress', 'water', 'nutrition', 'custom'
  )),
  value NUMERIC,
  text_value TEXT,
  unit TEXT,
  logged_at TIMESTAMPTZ DEFAULT NOW(),
  notes TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_manual_logs_user ON manual_health_logs(user_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_manual_logs_type ON manual_health_logs(user_id, log_type, logged_at DESC);

-- ============================================
-- WELLNESS SCORES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS wellness_scores (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  score_date DATE NOT NULL,
  overall_score NUMERIC NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
  sleep_score NUMERIC CHECK (sleep_score >= 0 AND sleep_score <= 100),
  activity_score NUMERIC CHECK (activity_score >= 0 AND activity_score <= 100),
  nutrition_score NUMERIC CHECK (nutrition_score >= 0 AND nutrition_score <= 100),
  mental_wellbeing_score NUMERIC CHECK (mental_wellbeing_score >= 0 AND mental_wellbeing_score <= 100),
  hydration_score NUMERIC CHECK (hydration_score >= 0 AND hydration_score <= 100),
  score_components JSONB DEFAULT '{}'::jsonb,
  trend TEXT CHECK (trend IN ('improving', 'stable', 'declining')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, score_date)
);

CREATE INDEX IF NOT EXISTS idx_wellness_scores_user ON wellness_scores(user_id, score_date DESC);

-- ============================================
-- ENHANCE INSIGHTS TABLE
-- ============================================
ALTER TABLE insights 
ADD COLUMN IF NOT EXISTS wellness_score NUMERIC,
ADD COLUMN IF NOT EXISTS related_goal_id UUID REFERENCES wellness_goals(id),
ADD COLUMN IF NOT EXISTS recommendation_type TEXT CHECK (
  recommendation_type IN ('improvement', 'maintenance', 'celebration', 'warning')
);

-- ============================================
-- EXTEND HEALTH METRICS TABLE
-- ============================================
-- Add new metric types support
ALTER TABLE health_metrics
DROP CONSTRAINT IF EXISTS health_metrics_metric_type_check;

ALTER TABLE health_metrics
ADD CONSTRAINT health_metrics_metric_type_check CHECK (
  metric_type IN (
    'steps', 'sleep_duration', 'active_energy', 
    'heart_rate', 'distance', 'heart_rate_variability',
    'water_intake', 'mood', 'stress_level', 'nutrition_calories',
    'nutrition_protein', 'nutrition_carbs', 'nutrition_fat'
  )
);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

-- Wellness Goals
ALTER TABLE wellness_goals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users manage own goals" ON wellness_goals;
CREATE POLICY "Users manage own goals" ON wellness_goals
  FOR ALL USING (auth.uid() = user_id);

-- Manual Health Logs
ALTER TABLE manual_health_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users manage own logs" ON manual_health_logs;
CREATE POLICY "Users manage own logs" ON manual_health_logs
  FOR ALL USING (auth.uid() = user_id);

-- Wellness Scores
ALTER TABLE wellness_scores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users view own scores" ON wellness_scores;
CREATE POLICY "Users view own scores" ON wellness_scores
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service can manage scores" ON wellness_scores;
CREATE POLICY "Service can manage scores" ON wellness_scores
  FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

-- ============================================
-- TRIGGERS
-- ============================================

-- Auto-update updated_at for wellness_goals
DROP TRIGGER IF EXISTS trigger_update_wellness_goals_updated_at ON wellness_goals;
CREATE TRIGGER trigger_update_wellness_goals_updated_at
  BEFORE UPDATE ON wellness_goals
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to calculate goal progress percentage
CREATE OR REPLACE FUNCTION calculate_goal_progress(
  p_goal_id UUID
) RETURNS NUMERIC AS $$
DECLARE
  v_goal wellness_goals;
  v_progress NUMERIC;
BEGIN
  SELECT * INTO v_goal FROM wellness_goals WHERE id = p_goal_id;
  
  IF NOT FOUND THEN
    RETURN 0;
  END IF;
  
  IF v_goal.target_value = 0 THEN
    RETURN 0;
  END IF;
  
  v_progress := (v_goal.current_value / v_goal.target_value) * 100;
  
  -- Cap at 100%
  IF v_progress > 100 THEN
    RETURN 100;
  END IF;
  
  RETURN v_progress;
END;
$$ LANGUAGE plpgsql;
