-- Migration: 022_waiting_messages
-- Description: Create waiting_messages table for queued coach messages
-- Date: 2026-02-09

-- Waiting messages table for messages to be delivered when user becomes active
CREATE TABLE IF NOT EXISTS waiting_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Message content
    message_text TEXT NOT NULL,
    message_type VARCHAR(50) DEFAULT 'coach_message', -- coach_message, coach_checkin, pattern_alert, accountability_nudge
    priority VARCHAR(20) DEFAULT 'normal', -- low, normal, high, urgent

    -- Scheduling
    scheduled_for TIMESTAMPTZ,

    -- Additional context 
    context JSONB DEFAULT '{}',

    -- Delivery tracking
    delivered BOOLEAN DEFAULT false,
    delivered_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_waiting_messages_user_delivered
    ON waiting_messages(user_id, delivered);

CREATE INDEX IF NOT EXISTS idx_waiting_messages_scheduled
    ON waiting_messages(scheduled_for)
    WHERE delivered = false;

-- Enable RLS
ALTER TABLE waiting_messages ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Users can view own waiting messages"
    ON waiting_messages FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can manage all
CREATE POLICY "Service role full access to waiting_messages"
    ON waiting_messages FOR ALL
    USING (auth.role() = 'service_role');

COMMENT ON TABLE waiting_messages IS 'Queued messages for delivery when user becomes active';
