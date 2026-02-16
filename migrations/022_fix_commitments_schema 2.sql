-- Migration: 022_fix_commitments_schema.sql
-- Purpose: Add missing commitment_text column to commitments table

-- Add commitment_text column if it doesn't exist
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS commitment_text TEXT;

-- If there's data in commitment_type but not commitment_text, copy it over
UPDATE commitments
SET commitment_text = commitment_type
WHERE commitment_text IS NULL AND commitment_type IS NOT NULL;

-- Add other potentially missing columns
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS extracted_from_message_id UUID;
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS completion_confidence FLOAT DEFAULT 0.5;
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Add indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_commitments_user_status ON commitments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_commitments_created_at ON commitments(created_at DESC);
