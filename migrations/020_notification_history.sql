-- Migration: 020_notification_history
-- Description: Create notification_history table to track sent notifications
-- Date: 2026-02-02

-- Notification history table
CREATE TABLE IF NOT EXISTS notification_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Notification details
    type VARCHAR(50) NOT NULL, -- 'task_reminder' | 'coach_nudge' | 'insight' | 'streak_alert' | 'coach_task'
    title TEXT NOT NULL,
    body TEXT NOT NULL,

    -- Reference to source (optional)
    reference_type VARCHAR(50), -- 'todo' | 'insight' | 'streak'
    reference_id UUID,

    -- Delivery tracking
    scheduled_for TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,

    -- Status
    status VARCHAR(20) DEFAULT 'pending', -- 'pending' | 'sent' | 'delivered' | 'failed' | 'cancelled'
    error_message TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_notification_history_user_status
    ON notification_history(user_id, status);

CREATE INDEX IF NOT EXISTS idx_notification_history_scheduled
    ON notification_history(scheduled_for)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_notification_history_user_created
    ON notification_history(user_id, created_at DESC);

-- Add notification count tracking to help with daily limits
CREATE INDEX IF NOT EXISTS idx_notification_history_daily_count
    ON notification_history(user_id, created_at)
    WHERE status IN ('sent', 'delivered');

-- Enable RLS
ALTER TABLE notification_history ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Users can view own notification history"
    ON notification_history FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can manage all notifications
CREATE POLICY "Service role can manage notifications"
    ON notification_history FOR ALL
    USING (auth.role() = 'service_role');

COMMENT ON TABLE notification_history IS 'Tracks all push notifications sent to users';
COMMENT ON COLUMN notification_history.type IS 'Type of notification: task_reminder, coach_nudge, insight, streak_alert, coach_task';
COMMENT ON COLUMN notification_history.status IS 'Delivery status: pending, sent, delivered, failed, cancelled';
