-- Migration 023: Daily/Weekly Message Limits
-- Free: 10/day, 30/week | Pro: 20/day, 100/week

-- Add daily/weekly tracking columns to existing table
ALTER TABLE user_message_limits
  ADD COLUMN IF NOT EXISTS daily_messages_used INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS weekly_messages_used INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS daily_limit INTEGER DEFAULT 10,
  ADD COLUMN IF NOT EXISTS weekly_limit INTEGER DEFAULT 30,
  ADD COLUMN IF NOT EXISTS last_daily_reset TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS last_weekly_reset TIMESTAMPTZ DEFAULT NOW();

-- Update existing pro users to have pro limits
UPDATE user_message_limits
SET daily_limit = 20, weekly_limit = 100
WHERE is_pro = TRUE;

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_message_limits_user_id
  ON user_message_limits(user_id);
