-- 034: Raise message limits — Free 5/15 → 10/25, Pro 10/30 → 25/60
UPDATE user_message_limits
SET daily_limit = 10, weekly_limit = 25
WHERE is_pro = FALSE;

UPDATE user_message_limits
SET daily_limit = 25, weekly_limit = 60
WHERE is_pro = TRUE;
