-- Migration: Add run_id and assistant_temp_id columns to messages table
-- This enables delta filtering for assistant messages and reconciliation similar to user messages

-- Migration ID: 20240107_add_run_id_assistant_temp_id
-- Target table: messages

-- 1. Add run_id column to store OpenAI run ID for delta filtering
ALTER TABLE messages ADD COLUMN IF NOT EXISTS run_id TEXT;

-- 2. Add assistant_temp_id column for client-side reconciliation
-- This is similar to client_temp_id for user messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS assistant_temp_id TEXT;

-- 3. Create index on run_id for efficient delta filtering queries
CREATE INDEX IF NOT EXISTS idx_messages_run_id ON messages(run_id);

-- 4. Create index on assistant_temp_id for efficient reconciliation lookups
CREATE INDEX IF NOT EXISTS idx_messages_assistant_temp_id ON messages(assistant_temp_id);

-- 5. Create composite index for common query patterns (user_id + run_id)
CREATE INDEX IF NOT EXISTS idx_messages_user_run ON messages(userid, run_id);

-- 6. Create index on chat_id + direction for message thread retrieval
CREATE INDEX IF NOT EXISTS idx_messages_chat_direction ON messages(chat_id, direction);

-- Verify the columns were added
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'messages' 
    AND column_name IN ('run_id', 'assistant_temp_id')
ORDER BY column_name;

-- Note: These indexes will help with:
-- - Delta filtering: WHERE run_id = ? (find messages from specific run)
-- - Reconciliation: WHERE assistant_temp_id = ? (match temp IDs to DB IDs)
-- - Thread retrieval: WHERE user_id = ? AND chat_id = ? ORDER BY created_at
