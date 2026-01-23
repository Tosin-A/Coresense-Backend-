-- Migration: 012_health_metrics_unique_index.sql
-- Purpose: Ensure unique constraint for health_metrics upserts

CREATE UNIQUE INDEX IF NOT EXISTS health_metrics_unique
ON health_metrics (user_id, metric_type, recorded_at);
