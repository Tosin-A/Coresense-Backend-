-- Migration 030: Lower free tier limits to 5/day, 15/week
-- Remove pro tier, all users get free limits

-- Update all users to new free limits
UPDATE user_message_limits
SET daily_limit = 5, weekly_limit = 15, is_pro = FALSE, pro_upgraded_at = NULL;