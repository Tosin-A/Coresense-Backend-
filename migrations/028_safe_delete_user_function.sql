-- Safe account deletion function
-- Runs as SECURITY DEFINER (postgres role) to bypass RLS and access auth schema.
-- Deletes all user data from application tables, then removes the auth.users row.
-- ON DELETE CASCADE on child FKs handles most cleanup automatically.
--
-- Tables that no longer exist are excluded. If you add new tables with user_id,
-- add a corresponding DELETE here.

CREATE OR REPLACE FUNCTION public.delete_user_account(target_user_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
BEGIN
    -- Application tables with user_id column
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

    -- Public users table (has FKs pointing to it from rate_limit_logs etc.)
    DELETE FROM public.users WHERE id = target_user_id;

    -- Finally delete the auth user (cascades to any remaining FK references)
    DELETE FROM auth.users WHERE id = target_user_id;
END;
$$;

-- Only allow the service_role (backend) to call this function
REVOKE ALL ON FUNCTION public.delete_user_account(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.delete_user_account(UUID) FROM anon;
REVOKE ALL ON FUNCTION public.delete_user_account(UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.delete_user_account(UUID) TO service_role;
