-- Add is_sandbox column to subscriptions table
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS is_sandbox BOOLEAN DEFAULT FALSE;
