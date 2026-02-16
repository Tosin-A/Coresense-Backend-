CREATE TABLE IF NOT EXISTS device_tokens (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    push_token text NOT NULL,
    platform text NOT NULL CHECK (platform IN ('ios', 'android')),
    active boolean DEFAULT true,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE(user_id, platform)
);
