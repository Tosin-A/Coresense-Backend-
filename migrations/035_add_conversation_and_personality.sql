-- Migration: Add conversation_id for Responses API and coach_personality preference
-- Part of Assistants API → Responses API migration

-- Add conversation_id column to assistant_threads for Responses API
ALTER TABLE assistant_threads ADD COLUMN IF NOT EXISTS conversation_id TEXT;

-- Add coach_personality to user_preferences (default: 'cora')
ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS coach_personality TEXT DEFAULT 'cora';
