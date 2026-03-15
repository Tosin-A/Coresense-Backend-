-- 033: Create habits and habit_completions tables
-- Supports daily/weekly habit tracking with streaks

CREATE TABLE IF NOT EXISTS habits (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title text NOT NULL CHECK (char_length(title) <= 200),
    icon text DEFAULT 'checkmark-circle-outline',
    frequency text NOT NULL DEFAULT 'daily' CHECK (frequency IN ('daily', 'weekly')),
    streak_count integer NOT NULL DEFAULT 0,
    longest_streak integer NOT NULL DEFAULT 0,
    last_completed_at timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS habit_completions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    habit_id uuid NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    completed_at timestamptz DEFAULT now(),
    date date NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(habit_id, date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_habits_user_active ON habits(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_habit_completions_habit_date ON habit_completions(habit_id, date);
CREATE INDEX IF NOT EXISTS idx_habit_completions_user_date ON habit_completions(user_id, date);

-- RLS policies
ALTER TABLE habits ENABLE ROW LEVEL SECURITY;
ALTER TABLE habit_completions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habits' AND policyname = 'habits_user_select') THEN
        CREATE POLICY habits_user_select ON habits FOR SELECT USING (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habits' AND policyname = 'habits_user_insert') THEN
        CREATE POLICY habits_user_insert ON habits FOR INSERT WITH CHECK (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habits' AND policyname = 'habits_user_update') THEN
        CREATE POLICY habits_user_update ON habits FOR UPDATE USING (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habits' AND policyname = 'habits_user_delete') THEN
        CREATE POLICY habits_user_delete ON habits FOR DELETE USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habit_completions' AND policyname = 'habit_completions_user_select') THEN
        CREATE POLICY habit_completions_user_select ON habit_completions FOR SELECT USING (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habit_completions' AND policyname = 'habit_completions_user_insert') THEN
        CREATE POLICY habit_completions_user_insert ON habit_completions FOR INSERT WITH CHECK (user_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'habit_completions' AND policyname = 'habit_completions_user_delete') THEN
        CREATE POLICY habit_completions_user_delete ON habit_completions FOR DELETE USING (user_id = auth.uid());
    END IF;
END $$;
