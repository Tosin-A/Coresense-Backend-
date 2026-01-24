-- Migration: 013_fix_health_metrics_fk.sql
-- Purpose: Fix incorrect FK on health_metrics

ALTER TABLE health_metrics
DROP CONSTRAINT IF EXISTS health_metrics_id_fkey;

ALTER TABLE health_metrics
ADD CONSTRAINT health_metrics_user_id_fkey
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_health_metrics_user_id
ON health_metrics(user_id);
