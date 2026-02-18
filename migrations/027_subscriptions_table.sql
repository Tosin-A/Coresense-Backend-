-- Migration: Create subscriptions table for Stripe integration
-- Tracks Stripe customer, subscription, and payment status per user.

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    stripe_price_id TEXT,
    status TEXT NOT NULL DEFAULT 'inactive',
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer
    ON subscriptions(stripe_customer_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription
    ON subscriptions(stripe_subscription_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_status
    ON subscriptions(status);

-- RLS: users can only read their own subscription
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY subscriptions_select_own ON subscriptions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY subscriptions_service_role ON subscriptions
    FOR ALL USING (true)
    WITH CHECK (true);
