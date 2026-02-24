-- Ensure insight_interactions table exists (was defined in 009 but may not have been run)
-- and update the delete_user_account RPC to handle it properly.

-- 1. Create insight_interactions if missing
CREATE TABLE IF NOT EXISTS insight_interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  insight_id UUID REFERENCES insights(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  interaction_type TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insight_interactions_user
  ON insight_interactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insight_interactions_insight
  ON insight_interactions(insight_id, interaction_type);

-- 2. Re-create the delete_user_account function with insight_interactions included
CREATE OR REPLACE FUNCTION public.delete_user_account(target_user_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
BEGIN
    -- Application tables with user_id column
    DELETE FROM insight_interactions    WHERE user_id = target_user_id;
    DELETE FROM subscriptions          WHERE user_id = target_user_id;
    DELETE FROM insights               WHERE user_id = target_user_id;
    DELETE FROM user_message_limits    WHERE user_id = target_user_id;
    DELETE FROM health_metrics         WHERE user_id = target_user_id;
    DELETE FROM user_metrics           WHERE user_id = target_user_id;
    DELETE FROM daily_stats            WHERE user_id = target_user_id;
    DELETE FROM user_preferences       WHERE user_id = target_user_id;
    DELETE FROM notification_preferences WHERE user_id = target_user_id;
    DELETE FROM device_tokens          WHERE user_id = target_user_id;
    DELETE FROM shared_todos           WHERE user_id = target_user_id;
    DELETE FROM user_streaks           WHERE user_id = target_user_id;
    DELETE FROM rate_limit_logs        WHERE user_id = target_user_id;

    -- Tables that use "userid" column
    DELETE FROM messages WHERE userid = target_user_id;

    -- Public users table
    DELETE FROM public.users WHERE id = target_user_id;

    -- Finally delete the auth user
    DELETE FROM auth.users WHERE id = target_user_id;
END;
$$;

-- Only allow the service_role (backend) to call this function
REVOKE ALL ON FUNCTION public.delete_user_account(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.delete_user_account(UUID) FROM anon;
REVOKE ALL ON FUNCTION public.delete_user_account(UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.delete_user_account(UUID) TO service_role;
