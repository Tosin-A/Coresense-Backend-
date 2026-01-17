-- Migration to add unique constraint to user_preferences table
-- This ensures upsert operations work correctly and prevent duplicate records

-- Check if the table exists first
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'user_preferences'
    ) THEN
        RAISE NOTICE 'user_preferences table exists, proceeding with migration';
    ELSE
        RAISE NOTICE 'user_preferences table does not exist, creating it first';
        
        -- Create the table if it doesn't exist
        CREATE TABLE user_preferences (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL,
            messaging_frequency INTEGER DEFAULT 3,
            messaging_style TEXT DEFAULT 'balanced',
            response_length TEXT DEFAULT 'medium',
            quiet_hours_enabled BOOLEAN DEFAULT false,
            quiet_hours_start TEXT DEFAULT '22:00',
            quiet_hours_end TEXT DEFAULT '07:00',
            quiet_hours_days INTEGER[] DEFAULT '{0,1,2,3,4,5,6}',
            accountability_level INTEGER DEFAULT 5,
            goals TEXT[] DEFAULT '{}',
            healthkit_enabled BOOLEAN DEFAULT false,
            healthkit_sync_frequency TEXT DEFAULT 'daily',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    END IF;
END $$
;

-- Add unique constraint on user_id to prevent duplicate preferences
-- This is required for upsert to work correctly
ALTER TABLE user_preferences 
ADD CONSTRAINT user_preferences_user_id_unique UNIQUE (user_id);

-- Enable RLS on user_preferences table
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Users can view and update their own preferences
DROP POLICY IF EXISTS "Users can manage own preferences" ON user_preferences;
CREATE POLICY "Users can manage own preferences" ON user_preferences
  FOR ALL USING (auth.uid() = user_id);

-- Service role can manage all preferences
DROP POLICY IF EXISTS "Service role full access" ON user_preferences;
CREATE POLICY "Service role full access" ON user_preferences
  FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_user_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER trigger_update_user_preferences_updated_at
  BEFORE UPDATE ON user_preferences
  FOR EACH ROW
  EXECUTE FUNCTION update_user_preferences_updated_at();