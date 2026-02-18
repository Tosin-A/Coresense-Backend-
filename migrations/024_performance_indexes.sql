-- Migration 024: Performance Indexes
-- Addresses N+1 query performance issues identified in audit

-- health_metrics: used heavily in /home/data, /insights, wellness queries
CREATE INDEX IF NOT EXISTS idx_health_metrics_user_type_date
  ON health_metrics(user_id, metric_type, recorded_at DESC);

-- messages: used in chat history, home screen last message
CREATE INDEX IF NOT EXISTS idx_messages_userid_created
  ON messages(userid, created_at DESC);

-- user_metrics: used in quick stats, analytics
CREATE INDEX IF NOT EXISTS idx_user_metrics_user_type_date
  ON user_metrics(user_id, metric_type, logged_at DESC);

-- insights: used in insights screen, home screen
CREATE INDEX IF NOT EXISTS idx_insights_user_created
  ON insights(user_id, created_at DESC);

-- insight_interactions: used to filter dismissed insights
CREATE INDEX IF NOT EXISTS idx_insight_interactions_user_type
  ON insight_interactions(user_id, interaction_type);
