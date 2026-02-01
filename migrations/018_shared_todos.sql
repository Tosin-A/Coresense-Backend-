-- Shared To-Do List between User and Coach
-- Migration: 018_shared_todos.sql

CREATE TABLE IF NOT EXISTS shared_todos (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title text NOT NULL,
    description text,
    created_by text NOT NULL CHECK (created_by IN ('user', 'coach')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    priority text NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    due_date date,
    due_time time,
    reminder_enabled boolean DEFAULT false,
    reminder_minutes_before int DEFAULT 30,
    coach_reasoning text,
    linked_insight_id text,
    completed_at timestamptz,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Index for efficient user + status queries
CREATE INDEX idx_shared_todos_user_status ON shared_todos(user_id, status);

-- Index for fetching pending todos by due date
CREATE INDEX idx_shared_todos_due_date ON shared_todos(user_id, due_date) WHERE status = 'pending';
