-- Migration: Add IAP (Apple/Google) columns to subscriptions table
-- Supports both Stripe and In-App Purchase as subscription sources

ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'stripe',
  ADD COLUMN IF NOT EXISTS apple_subscription_id TEXT,
  ADD COLUMN IF NOT EXISTS apple_transaction_id TEXT,
  ADD COLUMN IF NOT EXISTS apple_original_transaction_id TEXT;

CREATE INDEX IF NOT EXISTS idx_subscriptions_apple_subscription
  ON subscriptions(apple_subscription_id)
  WHERE apple_subscription_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_subscriptions_source
  ON subscriptions(source);

COMMENT ON COLUMN subscriptions.source IS 'stripe | apple';
COMMENT ON COLUMN subscriptions.apple_subscription_id IS 'Apple subscription group subscription ID';
COMMENT ON COLUMN subscriptions.apple_transaction_id IS 'Latest StoreKit 2 transaction ID';
COMMENT ON COLUMN subscriptions.apple_original_transaction_id IS 'Original transaction ID for subscription lineage';
