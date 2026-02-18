-- Enable Row Level Security on device_tokens and shared_todos tables
-- These tables were missing RLS policies, allowing any authenticated user to query all rows

-- device_tokens: stores push notification tokens per user
ALTER TABLE IF EXISTS device_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Users manage own device tokens"
    ON device_tokens FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY IF NOT EXISTS "Service role full access to device_tokens"
    ON device_tokens FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- shared_todos: stores user and coach-created tasks
ALTER TABLE IF EXISTS shared_todos ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Users manage own todos"
    ON shared_todos FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY IF NOT EXISTS "Service role full access to shared_todos"
    ON shared_todos FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');
