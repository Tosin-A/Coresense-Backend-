-- Add notification preference columns to user_preferences
-- These columns back the notification toggles in the Settings screen

ALTER TABLE user_preferences
  ADD COLUMN IF NOT EXISTS push_notifications boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS task_reminders boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS weekly_reports boolean DEFAULT true;
