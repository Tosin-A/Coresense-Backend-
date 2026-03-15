-- 034: Raise free-tier message limits from 5/15 to 10/25
UPDATE user_message_limits
SET daily_limit = 10, weekly_limit = 25
WHERE is_pro = FALSE;
