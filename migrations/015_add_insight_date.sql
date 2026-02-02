-- Migration: 015_add_insight_date.sql
-- Description: Add insight_date column to insights and backfill from created_at
-- Date: 2026-01-26

ALTER TABLE insights
ADD COLUMN IF NOT EXISTS insight_date DATE;

UPDATE insights
SET insight_date = COALESCE(insight_date, created_at::date)
WHERE insight_date IS NULL;

ALTER TABLE insights
ALTER COLUMN insight_date SET DEFAULT CURRENT_DATE;

CREATE INDEX IF NOT EXISTS idx_insights_date
ON insights(user_id, insight_date DESC);
