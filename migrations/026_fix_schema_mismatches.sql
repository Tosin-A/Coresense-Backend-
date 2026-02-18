-- Migration 026: Fix schema mismatches between code and database
-- Adds missing columns that the application code expects

-- 1. user_message_limits: add daily/weekly tracking columns
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS daily_messages_used INTEGER DEFAULT 0;
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS weekly_messages_used INTEGER DEFAULT 0;
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS daily_limit INTEGER DEFAULT 10;
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS weekly_limit INTEGER DEFAULT 30;
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS last_daily_reset TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS last_weekly_reset TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE user_message_limits ADD COLUMN IF NOT EXISTS pro_upgraded_at TIMESTAMPTZ;

-- Backfill daily/weekly from existing messages_used
UPDATE user_message_limits
SET daily_messages_used = COALESCE(messages_used, 0),
    weekly_messages_used = COALESCE(messages_used, 0)
WHERE daily_messages_used = 0 AND COALESCE(messages_used, 0) > 0;

-- 2. commitments: add commitment_text column
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS commitment_text TEXT;

-- Backfill from commitment_type if commitment_text is null
UPDATE commitments
SET commitment_text = commitment_type
WHERE commitment_text IS NULL AND commitment_type IS NOT NULL;

-- 3. insights: add body and actionable columns
ALTER TABLE insights ADD COLUMN IF NOT EXISTS body TEXT;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS actionable BOOLEAN DEFAULT FALSE;

-- Backfill body from description or title if available
UPDATE insights
SET body = COALESCE(description, title)
WHERE body IS NULL;
