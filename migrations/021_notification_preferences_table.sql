-- Migration: 021_notification_preferences_table
-- Description: Create dedicated notification_preferences table
-- Date: 2026-02-02

-- Create notification_preferences table with all notification settings
CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Master toggle
    notifications_enabled BOOLEAN DEFAULT true,

    -- Category toggles
    task_reminders_enabled BOOLEAN DEFAULT true,
    coach_nudges_enabled BOOLEAN DEFAULT true,
    insights_enabled BOOLEAN DEFAULT true,
    streak_reminders_enabled BOOLEAN DEFAULT true,

    -- Quiet hours
    quiet_hours_enabled BOOLEAN DEFAULT false,
    quiet_hours_start TIME DEFAULT '22:00',
    quiet_hours_end TIME DEFAULT '08:00',

    -- Frequency limits
    max_daily_notifications INTEGER DEFAULT 10,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure one row per user
    UNIQUE(user_id)
);

-- Create index for efficient user lookups
CREATE INDEX IF NOT EXISTS idx_notification_preferences_user
    ON notification_preferences(user_id);

-- Enable RLS
ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Users can view own notification preferences"
    ON notification_preferences FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own notification preferences"
    ON notification_preferences FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own notification preferences"
    ON notification_preferences FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Service role can manage all
CREATE POLICY "Service role full access to notification_preferences"
    ON notification_preferences FOR ALL
    USING (auth.role() = 'service_role');

COMMENT ON TABLE notification_preferences IS 'User notification preferences for push notifications';
