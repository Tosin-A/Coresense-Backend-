-- ============================================================================
-- Cost Tracking Monitoring Queries
-- Use these to track OpenAI cost optimization progress
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Daily Cost Summary (Most Important)
-- ----------------------------------------------------------------------------

-- Shows daily cost breakdown by API type
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_calls,
    COUNT(CASE WHEN cached = true THEN 1 END) as cached_calls,
    COUNT(CASE WHEN cached = false THEN 1 END) as api_calls,
    SUM(tokens_generated + tokens_input) as total_tokens,
    -- Cost calculation (adjust rates as needed)
    SUM(
        CASE 
            WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
            WHEN model_path LIKE '%gpt-4o-mini%' OR model_path LIKE '%gpt-3.5%' THEN 
                ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
            ELSE 0.001  -- Default estimate
        END
    ) as estimated_daily_cost,
    ROUND(
        COUNT(CASE WHEN cached = true THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as cache_hit_rate_pct
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;


-- ----------------------------------------------------------------------------
-- 2. API Type Distribution
-- ----------------------------------------------------------------------------

-- Shows what percentage of calls use each API type
SELECT 
    CASE 
        WHEN metadata->>'api_type' = 'assistant' THEN 'Assistant API'
        WHEN metadata->>'api_type' = 'completions' THEN 'Completions API'
        WHEN metadata->>'api_type' = 'pattern' THEN 'Pattern Cache'
        WHEN cached = true THEN 'Response Cache'
        ELSE 'Unknown'
    END as api_type,
    COUNT(*) as call_count,
    ROUND(COUNT(*)::float / SUM(COUNT(*)) OVER () * 100, 2) as percentage,
    SUM(tokens_generated + tokens_input) as total_tokens,
    ROUND(AVG(tokens_generated + tokens_input), 0) as avg_tokens_per_call,
    -- Estimated cost per API type
    SUM(
        CASE 
            WHEN metadata->>'api_type' = 'assistant' THEN 0.009  -- ~0.9 cents
            WHEN metadata->>'api_type' = 'completions' THEN 0.0015  -- ~0.15 cents
            ELSE 0  -- Cached = free
        END
    ) as estimated_cost
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY api_type
ORDER BY call_count DESC;


-- ----------------------------------------------------------------------------
-- 3. Cost by User Tier (Free vs Pro)
-- ----------------------------------------------------------------------------

SELECT 
    CASE WHEN uml.is_pro THEN 'Pro' ELSE 'Free' END as user_tier,
    COUNT(DISTINCT acl.user_id) as unique_users,
    COUNT(*) as total_calls,
    ROUND(AVG(acl.tokens_generated + acl.tokens_input), 0) as avg_tokens_per_call,
    SUM(acl.tokens_generated + acl.tokens_input) as total_tokens,
    -- Estimated cost
    ROUND(
        SUM(
            CASE 
                WHEN acl.model_path LIKE '%gpt-4%' AND acl.model_path NOT LIKE '%mini%' THEN 
                    ((acl.tokens_input * 0.00003) + (acl.tokens_generated * 0.00006))
                WHEN acl.model_path LIKE '%gpt-4o-mini%' THEN 
                    ((acl.tokens_input * 0.00000015) + (acl.tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ),
        2
    ) as estimated_cost
FROM ai_call_logs acl
LEFT JOIN user_message_limits uml ON acl.user_id = uml.user_id
WHERE acl.created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY user_tier
ORDER BY estimated_cost DESC;


-- ----------------------------------------------------------------------------
-- 4. Cache Hit Rate Trend (7-day rolling)
-- ----------------------------------------------------------------------------

SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_calls,
    COUNT(CASE WHEN cached = true THEN 1 END) as cache_hits,
    ROUND(
        COUNT(CASE WHEN cached = true THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as cache_hit_rate_pct,
    -- Calculate potential savings from cache hits
    COUNT(CASE WHEN cached = true THEN 1 END) * 0.009 as estimated_savings
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;


-- ----------------------------------------------------------------------------
-- 5. Most Expensive Users (Cost per user)
-- ----------------------------------------------------------------------------

SELECT 
    user_id,
    COUNT(*) as call_count,
    SUM(tokens_generated + tokens_input) as total_tokens,
    ROUND(AVG(tokens_generated + tokens_input), 0) as avg_tokens,
    COUNT(CASE WHEN cached = true THEN 1 END) as cached_calls,
    ROUND(
        COUNT(CASE WHEN cached = true THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as cache_hit_rate_pct,
    -- Estimated cost per user
    ROUND(
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ),
        4
    ) as estimated_cost
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY user_id
ORDER BY estimated_cost DESC
LIMIT 20;


-- ----------------------------------------------------------------------------
-- 6. Model Usage Distribution
-- ----------------------------------------------------------------------------

SELECT 
    model_path,
    COUNT(*) as call_count,
    ROUND(COUNT(*)::float / SUM(COUNT(*)) OVER () * 100, 2) as percentage,
    SUM(tokens_generated + tokens_input) as total_tokens,
    ROUND(AVG(tokens_generated + tokens_input), 0) as avg_tokens,
    -- Cost by model
    ROUND(
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' OR model_path LIKE '%gpt-3.5%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ),
        2
    ) as estimated_cost
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY model_path
ORDER BY call_count DESC;


-- ----------------------------------------------------------------------------
-- 7. Response Time vs Cost Analysis
-- ----------------------------------------------------------------------------

SELECT 
    CASE 
        WHEN response_time_ms < 1000 THEN '< 1s'
        WHEN response_time_ms < 2000 THEN '1-2s'
        WHEN response_time_ms < 3000 THEN '2-3s'
        WHEN response_time_ms < 5000 THEN '3-5s'
        ELSE '> 5s'
    END as response_time_bucket,
    COUNT(*) as call_count,
    ROUND(AVG(tokens_generated + tokens_input), 0) as avg_tokens,
    ROUND(AVG(response_time_ms), 0) as avg_response_time_ms,
    -- Calculate cost
    ROUND(
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ),
        2
    ) as estimated_cost
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
  AND response_time_ms IS NOT NULL
GROUP BY response_time_bucket
ORDER BY avg_response_time_ms;


-- ----------------------------------------------------------------------------
-- 8. Hourly Usage Pattern (Find peak times)
-- ----------------------------------------------------------------------------

SELECT 
    EXTRACT(HOUR FROM created_at) as hour_of_day,
    COUNT(*) as call_count,
    COUNT(CASE WHEN cached = true THEN 1 END) as cache_hits,
    ROUND(
        COUNT(CASE WHEN cached = true THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as cache_hit_rate_pct,
    SUM(tokens_generated + tokens_input) as total_tokens,
    -- Estimated cost by hour
    ROUND(
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ),
        2
    ) as estimated_cost
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY hour_of_day
ORDER BY hour_of_day;


-- ----------------------------------------------------------------------------
-- 9. Success Rate by API Type
-- ----------------------------------------------------------------------------

SELECT 
    CASE 
        WHEN metadata->>'api_type' = 'assistant' THEN 'Assistant API'
        WHEN metadata->>'api_type' = 'completions' THEN 'Completions API'
        WHEN cached = true THEN 'Cached'
        ELSE 'Unknown'
    END as api_type,
    COUNT(*) as total_calls,
    COUNT(CASE WHEN success = true THEN 1 END) as successful_calls,
    ROUND(
        COUNT(CASE WHEN success = true THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as success_rate_pct,
    COUNT(CASE WHEN success = false THEN 1 END) as failed_calls,
    ROUND(AVG(response_time_ms), 0) as avg_response_time_ms
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY api_type
ORDER BY total_calls DESC;


-- ----------------------------------------------------------------------------
-- 10. Before/After Comparison (Set optimization start date)
-- ----------------------------------------------------------------------------

-- Replace 'YYYY-MM-DD' with your optimization start date
WITH optimization_date AS (
    SELECT '2024-01-15'::date as start_date  -- UPDATE THIS DATE
),
before_period AS (
    SELECT 
        COUNT(*) as calls,
        SUM(tokens_generated + tokens_input) as tokens,
        COUNT(CASE WHEN cached = true THEN 1 END) as cache_hits,
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ) as cost
    FROM ai_call_logs
    WHERE created_at >= (SELECT start_date FROM optimization_date) - INTERVAL '7 days'
      AND created_at < (SELECT start_date FROM optimization_date)
),
after_period AS (
    SELECT 
        COUNT(*) as calls,
        SUM(tokens_generated + tokens_input) as tokens,
        COUNT(CASE WHEN cached = true THEN 1 END) as cache_hits,
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ) as cost
    FROM ai_call_logs
    WHERE created_at >= (SELECT start_date FROM optimization_date)
      AND created_at < (SELECT start_date FROM optimization_date) + INTERVAL '7 days'
)
SELECT 
    'Before Optimization' as period,
    b.calls as total_calls,
    b.tokens as total_tokens,
    ROUND(b.cost, 2) as estimated_cost,
    ROUND(b.cache_hits::float / b.calls * 100, 2) as cache_hit_rate_pct
FROM before_period b
UNION ALL
SELECT 
    'After Optimization' as period,
    a.calls as total_calls,
    a.tokens as total_tokens,
    ROUND(a.cost, 2) as estimated_cost,
    ROUND(a.cache_hits::float / a.calls * 100, 2) as cache_hit_rate_pct
FROM after_period a
UNION ALL
SELECT 
    'Improvement' as period,
    a.calls - b.calls as total_calls,
    a.tokens - b.tokens as total_tokens,
    ROUND(a.cost - b.cost, 2) as cost_change,
    ROUND((b.cost - a.cost) / b.cost * 100, 2) as cost_reduction_pct
FROM before_period b, after_period a;


-- ----------------------------------------------------------------------------
-- 11. Monthly Cost Projection
-- ----------------------------------------------------------------------------

-- Projects monthly cost based on last 7 days
WITH last_7_days AS (
    SELECT 
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ) as cost_7_days
    FROM ai_call_logs
    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT 
    ROUND(cost_7_days, 2) as cost_last_7_days,
    ROUND(cost_7_days / 7, 4) as avg_daily_cost,
    ROUND((cost_7_days / 7) * 30, 2) as projected_monthly_cost,
    ROUND((cost_7_days / 7) * 365, 2) as projected_yearly_cost
FROM last_7_days;


-- ----------------------------------------------------------------------------
-- 12. Cache Performance by Pattern Type
-- ----------------------------------------------------------------------------

-- Requires pattern type to be logged in metadata
SELECT 
    metadata->>'pattern_type' as pattern_type,
    COUNT(*) as total_uses,
    ROUND(COUNT(*)::float / SUM(COUNT(*)) OVER () * 100, 2) as percentage,
    -- Calculate savings (assume each cache hit saves 0.009)
    COUNT(*) * 0.009 as estimated_savings
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
  AND cached = true
  AND metadata->>'pattern_type' IS NOT NULL
GROUP BY pattern_type
ORDER BY total_uses DESC;


-- ----------------------------------------------------------------------------
-- 13. Function Calling Frequency (Assistant API overhead)
-- ----------------------------------------------------------------------------

SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_calls,
    COUNT(CASE WHEN metadata->>'function_calls' IS NOT NULL THEN 1 END) as calls_with_functions,
    ROUND(
        COUNT(CASE WHEN metadata->>'function_calls' IS NOT NULL THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as function_call_percentage
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;


-- ----------------------------------------------------------------------------
-- 14. Cost Savings Dashboard (Single View)
-- ----------------------------------------------------------------------------

-- All key metrics in one view
SELECT 
    COUNT(*) as total_calls_7d,
    COUNT(CASE WHEN cached = true THEN 1 END) as cache_hits,
    ROUND(
        COUNT(CASE WHEN cached = true THEN 1 END)::float / COUNT(*) * 100, 
        2
    ) as cache_hit_rate_pct,
    SUM(tokens_generated + tokens_input) as total_tokens,
    ROUND(AVG(tokens_generated + tokens_input), 0) as avg_tokens_per_call,
    ROUND(
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ),
        2
    ) as estimated_cost_7d,
    ROUND(
        SUM(
            CASE 
                WHEN model_path LIKE '%gpt-4%' AND model_path NOT LIKE '%mini%' THEN 
                    ((tokens_input * 0.00003) + (tokens_generated * 0.00006))
                WHEN model_path LIKE '%gpt-4o-mini%' THEN 
                    ((tokens_input * 0.00000015) + (tokens_generated * 0.0000006))
                ELSE 0.001
            END
        ) / 7 * 30,
        2
    ) as projected_monthly_cost,
    -- Calculate potential savings from cache hits (assume 0.009 per call)
    ROUND(COUNT(CASE WHEN cached = true THEN 1 END) * 0.009, 2) as savings_from_cache_7d,
    ROUND(AVG(response_time_ms), 0) as avg_response_time_ms
FROM ai_call_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days';
c                                                                                                                                                                                                                                                      