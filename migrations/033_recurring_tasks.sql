-- 033: Add recurring task support to shared_todos
-- Replaces standalone habits system with recurring tasks

-- Add recurring columns to shared_todos
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN DEFAULT FALSE;
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS frequency TEXT DEFAULT 'daily';
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS streak_count INTEGER DEFAULT 0;
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS longest_streak INTEGER DEFAULT 0;
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS icon TEXT;
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;
ALTER TABLE shared_todos ADD COLUMN IF NOT EXISTS weekly_target INTEGER DEFAULT 7;

-- Create task_completions table (tracks daily completions for recurring tasks)
CREATE TABLE IF NOT EXISTS task_completions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES shared_todos(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    completed_at timestamptz DEFAULT now(),
    date date NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(task_id, date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_task_completions_task_date ON task_completions(task_id, date);
CREATE INDEX IF NOT EXISTS idx_task_completions_user_date ON task_completions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_shared_todos_recurring ON shared_todos(user_id, is_recurring) WHERE is_recurring = TRUE;

-- RLS policies for task_completions
ALTER TABLE task_completions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'task_completions' AND policyname = 'task_completions_user_select') THEN
        CREATE POLICY task_completions_user_select ON task_completions FOR SELECT USING (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'task_completions' AND policyname = 'task_completions_user_insert') THEN
        CREATE POLICY task_completions_user_insert ON task_completions FOR INSERT WITH CHECK (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'task_completions' AND policyname = 'task_completions_user_delete') THEN
        CREATE POLICY task_completions_user_delete ON task_completions FOR DELETE USING (user_id = auth.uid());
    END IF;
END $$;
