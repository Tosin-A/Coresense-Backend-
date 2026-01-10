-- Migration: Simplified User Streaks Schema
-- This migration replaces the complex multi-type streak system with a simple per-user streak

-- ============================================
-- Step 1: Create the new simplified table
-- ============================================

CREATE TABLE IF NOT EXISTS user_streaks_new (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_activity_date DATE,
    user_timezone TEXT DEFAULT 'UTC',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Step 2: Migrate existing data (if any)
-- ============================================

-- Copy check_in streak data from old table to new table
INSERT INTO user_streaks_new (user_id, current_streak, longest_streak, last_activity_date, user_timezone)
SELECT 
    user_id,
    COALESCE(current_streak, 0),
    COALESCE(longest_streak, 0),
    last_activity_date,
    'UTC' as user_timezone
FROM user_streaks
WHERE streak_type = 'check_in'
ON CONFLICT (user_id) DO UPDATE SET
    current_streak = COALESCE(EXCLUDED.current_streak, 0),
    longest_streak = COALESCE(EXCLUDED.longest_streak, 0),
    last_activity_date = EXCLUDED.last_activity_date;

-- ============================================
-- Step 3: Drop old table and rename new table
-- ============================================

DROP TABLE IF EXISTS user_streaks CASCADE;
ALTER TABLE user_streaks_new RENAME TO user_streaks;

-- ============================================
-- Step 4: Recreate the streak update function with timezone support
-- ============================================

DROP FUNCTION IF EXISTS update_user_streak CASCADE;

CREATE OR REPLACE FUNCTION update_user_streak(
    p_user_id UUID,
    p_user_timezone TEXT DEFAULT 'UTC'
) RETURNS JSONB AS $$
DECLARE
    v_current_streak INTEGER;
    v_longest_streak INTEGER;
    v_last_date DATE;
    v_today DATE;
    v_new_streak INTEGER;
BEGIN
    -- Get today's date in user's timezone
    v_today := CURRENT_DATE AT TIME ZONE p_user_timezone;
    
    -- Get current streak info
    SELECT current_streak, longest_streak, last_activity_date
    INTO v_current_streak, v_longest_streak, v_last_date
    FROM user_streaks
    WHERE user_id = p_user_id;
    
    IF NOT FOUND THEN
        -- Create new streak record
        INSERT INTO user_streaks (user_id, current_streak, longest_streak, last_activity_date, user_timezone)
        VALUES (p_user_id, 1, 1, v_today, p_user_timezone);
        
        v_new_streak := 1;
    ELSIF v_last_date = v_today THEN
        -- Already counted today, return current streak
        v_new_streak := v_current_streak;
    ELSIF v_last_date = v_today - 1 THEN
        -- Consecutive day, increment streak
        v_new_streak := v_current_streak + 1;
        
        UPDATE user_streaks
        SET current_streak = v_new_streak,
            longest_streak = GREATEST(v_longest_streak, v_new_streak),
            last_activity_date = v_today,
            user_timezone = p_user_timezone,
            updated_at = NOW()
        WHERE user_id = p_user_id;
    ELSE
        -- Streak broken, reset to 1
        v_new_streak := 1;
        
        UPDATE user_streaks
        SET current_streak = 1,
            longest_streak = GREATEST(v_longest_streak, 1),
            last_activity_date = v_today,
            user_timezone = p_user_timezone,
            updated_at = NOW()
        WHERE user_id = p_user_id;
    END IF;
    
    -- Return updated streak data as JSON
    RETURN jsonb_build_object(
        'current_streak', v_new_streak,
        'longest_streak', COALESCE(v_longest_streak, 0),
        'last_activity_date', v_today::TEXT,
        'user_timezone', p_user_timezone
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Step 5: Create function to get user streak
-- ============================================

DROP FUNCTION IF EXISTS get_user_streak CASCADE;

CREATE OR REPLACE FUNCTION get_user_streak(p_user_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'current_streak', COALESCE(current_streak, 0),
        'longest_streak', COALESCE(longest_streak, 0),
        'last_activity_date', COALESCE(last_activity_date::TEXT, NULL::TEXT),
        'user_timezone', COALESCE(user_timezone, 'UTC')
    ) INTO v_result
    FROM user_streaks
    WHERE user_id = p_user_id;
    
    IF v_result IS NULL THEN
        RETURN jsonb_build_object(
            'current_streak', 0,
            'longest_streak', 0,
            'last_activity_date', NULL,
            'user_timezone', 'UTC'
        );
    END IF;
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Step 6: Update RLS policies
-- ============================================

ALTER TABLE user_streaks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own streaks" ON user_streaks;
CREATE POLICY "Users manage own streaks" ON user_streaks
    FOR ALL USING (auth.uid() = user_id);

-- ============================================
-- Step 7: Update trigger for updated_at
-- ============================================

DROP TRIGGER IF EXISTS trigger_update_user_streaks_updated_at ON user_streaks;
CREATE TRIGGER trigger_update_user_streaks_updated_at
    BEFORE UPDATE ON user_streaks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Done
SELECT 'Streak schema migration complete' as status;
