"""
CoreSense App API Endpoints
Handles all mobile app data requests with real user data only.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel
import logging

from backend.database.supabase_client import get_supabase_client
from backend.services.user_initialization_service import initialize_new_user
from backend.middleware.auth_helper import get_current_user_id
from backend.utils.supabase_utils import extract_supabase_data, get_first_item_or_none
from backend.utils.exceptions import DatabaseError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["app"])





# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    timezone: Optional[str] = None
    phone_number: Optional[str] = None


class PreferencesUpdateRequest(BaseModel):
    messaging_style: Optional[str] = None
    messaging_frequency: Optional[int] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    accountability_level: Optional[int] = None
    goals: Optional[List[str]] = None
    healthkit_enabled: Optional[bool] = None


class HealthMetricIn(BaseModel):
    metric_type: str
    value: float
    unit: str
    recorded_at: datetime
    source: Optional[str] = "healthkit"
    metadata: Optional[dict] = None


class HealthSyncRequest(BaseModel):
    metrics: List[HealthMetricIn]


class MetricLogRequest(BaseModel):
    """Request to log a single metric."""
    metric_type: str  # 'energy', 'mood', 'sleep', 'stress', 'focus'
    value: float
    notes: Optional[str] = None
    context: Optional[dict] = None


class MetricBatchRequest(BaseModel):
    """Request to log multiple metrics at once."""
    metrics: List[MetricLogRequest]



# ============================================
# HOME SCREEN ENDPOINTS
# ============================================

@router.get("/home/data")
async def get_home_data(user_id: str = Depends(get_current_user_id)):
    """Get all data needed for home screen - real user data only."""
    try:
        supabase = get_supabase_client()
        
        # Get last coach message (supports direction or sender_type)
        try:
            messages_response = (
                supabase
                .table('messages')
                .select('*')
                .eq('userid', user_id)
                .or_('direction.eq.outgoing,sender_type.eq.gpt')
                .order('created_at', desc=True)
                .limit(1)
                .execute()
            )
            
            last_message = None
            if messages_response.data:
                msg = messages_response.data[0]
                direction = msg.get('direction') or (
                    'incoming' if msg.get('sender_type') == 'user'
                    else 'outgoing' if msg.get('sender_type') == 'gpt'
                    else None
                )
                # Only return coach->user (outgoing) as lastCoachMessage
                if direction == 'outgoing':
                    last_message = {
                        "id": msg['chat_id'],            # Changed from 'id' to 'chat_id'
                        "text": msg.get('content', msg.get('message_text', '')),  # Support both new and old schema
                        "timestamp": msg['created_at'],
                        "read": msg.get('read_in_app', False)
                    }
        except Exception as e:
            logger.warning(f"Could not fetch coach messages: {e}")
            last_message = None
        
        # Get today's insight
        try:
            # Use created_at range to avoid hard dependency on insight_date column.
            today = datetime.now(timezone.utc).date()
            start_of_day = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat()
            end_of_day = (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)).isoformat()
            # Fetch today's insights, excluding dismissed ones via insight_interactions
            insights_response = (
                supabase.table('insights')
                .select('*')
                .eq('user_id', user_id)
                .gte('created_at', start_of_day)
                .lt('created_at', end_of_day)
                .order('priority', desc=True)
                .limit(5)
                .execute()
            )

            today_insight = None
            if insights_response.data:
                # Get dismissed insight IDs from insight_interactions
                dismissed_response = (
                    supabase.table('insight_interactions')
                    .select('insight_id')
                    .eq('user_id', user_id)
                    .eq('interaction_type', 'dismissed')
                    .execute()
                )
                dismissed_ids = {r['insight_id'] for r in (dismissed_response.data or [])}

                # Find the first non-dismissed insight
                for insight in insights_response.data:
                    if insight['id'] not in dismissed_ids:
                        today_insight = {
                            "id": insight['id'],
                            "title": insight['title'],
                            "body": insight['body'],
                            "category": insight['insight_type'],
                            "actionable": insight.get('actionable', False)
                        }
                        break
        except Exception as e:
            logger.warning(f"Could not fetch insights: {e}")
            today_insight = None
        
        # Get user streak (simplified schema only)
        current_streak = 0
        try:
            streak_response = (
                supabase.table('user_streaks')
                .select('current_streak')
                .eq('user_id', user_id)
                .limit(1)
                .execute()
            )
            if streak_response.data and len(streak_response.data) > 0:
                current_streak = streak_response.data[0].get('current_streak', 0)
        except Exception as e:
            logger.warning(f"Could not fetch streak: {e}")
            current_streak = 0
        
        # Get today's completed check-ins count
        try:
            checkins_response = (
                supabase.table('daily_stats')
                .select('check_ins')
                .eq('user_id', user_id)
                .eq('stat_date', date.today().isoformat())
                .limit(1)
                .execute()
            )
            completed_today = 0
            if checkins_response.data:
                completed_today = checkins_response.data[0].get('check_ins', 0)
        except Exception as e:
            logger.warning(f"Could not fetch check-ins: {e}")
            completed_today = 0
        
        # Get user's sleep data from health_metrics (last night)
        try:
            start = datetime.combine(date.today() - timedelta(days=1), datetime.min.time()).isoformat()
            end = datetime.combine(date.today(), datetime.min.time()).isoformat()
            sleep_response = (
                supabase.table('health_metrics')
                .select('value,recorded_at')
                .eq('user_id', user_id)
                .eq('metric_type', 'sleep_duration')
                .gte('recorded_at', start)
                .lt('recorded_at', end)
                .order('recorded_at', desc=True)
                .execute()
            )
            sleep_hours = None
            if sleep_response.data:
                # If your values are minutes, convert to hours; if already hours, keep as-is.
                # Example assumes hours:
                sleep_hours = round(float(sleep_response.data[0]['value']), 2)
        except Exception as e:
            logger.warning(f"Could not fetch health metrics: {e}")
            sleep_hours = None
        
        return {
            "lastCoachMessage": last_message,
            "todayInsight": today_insight,
            "streak": current_streak,
            "completedToday": completed_today,
            "sleepHours": sleep_hours
        }
        
    except Exception as e:
        logger.error(f"Error fetching home data: {e}")
        return {
            "lastCoachMessage": None,
            "todayInsight": None,
            "streak": 0,
            "completedToday": 0,
            "sleepHours": None
        }


# ============================================
# INSIGHTS ENDPOINTS
# ============================================

@router.get("/insights")
async def get_insights(user_id: str = Depends(get_current_user_id)):
    """
    Get insights for insights screen - real user data only.
    
    Optimizations:
    1. Calculate wellness score ONCE and pass to generate_insights()
    2. This avoids duplicate calculation that was causing 2x workload
    """
    try:
        # Calculate wellness score ONCE (this is cached, so subsequent calls are fast)
        from backend.services.wellness_analytics_service import wellness_analytics_service
        wellness_score = await wellness_analytics_service.calculate_wellness_score(user_id)
        
        # Generate insights, passing the pre-calculated score
        # This is the KEY optimization - no duplicate calculation!
        from backend.services.insight_generation_service import insight_generation_service
        generated_insights = await insight_generation_service.generate_insights(
            user_id, "weekly", wellness_score=wellness_score
        )
        
        # Convert generated insights to pattern format
        patterns = []
        for insight in generated_insights[:5]:  # Top 5
            patterns.append({
                "id": f"generated-{insight.get('title', '').lower().replace(' ', '-')}",
                "title": insight['title'],
                "category": insight['category'],
                "interpretation": insight['body'],
                "expandedContent": None,
                "trend": insight.get('trend', 'stable'),
                "trendValue": insight.get('trend_value'),
                "dataPoints": [],
                "actionable": insight.get('actionable', False),
                "actionText": insight.get('action_text')
            })
        
        # Get actionable insight (highest priority actionable one)
        actionable = None
        if generated_insights:
            actionable_insights = [i for i in generated_insights if i.get('actionable')]
            if actionable_insights:
                top_actionable = max(actionable_insights, key=lambda x: x.get('priority', 0))
                actionable = {
                    "id": f"actionable-{top_actionable['title'].lower().replace(' ', '-')}",
                    "title": top_actionable['title'],
                    "body": top_actionable['body'],
                    "actionText": top_actionable.get('action_text')
                }
        
        # Get saved insights count
        saved_response = get_supabase_client().table('insights').select('id').eq(
            'user_id', user_id
        ).eq('saved', True).execute()
        
        saved_count = len(saved_response.data) if saved_response.data else 0
        
        return {
            "wellnessScore": {
                "overall": wellness_score.overall,
                "sleep": wellness_score.sleep,
                "activity": wellness_score.activity,
                "nutrition": wellness_score.nutrition,
                "mental": wellness_score.mental,
                "hydration": wellness_score.hydration,
                "trend": wellness_score.trend
            },
            "weeklySummary": None,
            "patterns": patterns,
            "actionable": actionable,
            "savedCount": saved_count
        }
        
    except Exception as e:
        logger.error(f"Error fetching insights: {e}")
        raise DatabaseError("Failed to fetch insights", original_error=e)


@router.post("/insights/{insight_id}/save")
async def save_insight(insight_id: str, user_id: str = Depends(get_current_user_id)):
    """Save an insight to favorites."""
    try:
        get_supabase_client().table('insights').update({
            'saved': True,
            'saved_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', insight_id).eq('user_id', user_id).execute()
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error saving insight: {e}")
        raise DatabaseError("Failed to save insight", original_error=e)


@router.post("/insights/{insight_id}/dismiss")
async def dismiss_insight(insight_id: str, user_id: str = Depends(get_current_user_id)):
    """Dismiss an insight by recording a dismissed interaction."""
    try:
        get_supabase_client().table('insight_interactions').insert({
            'insight_id': insight_id,
            'user_id': user_id,
            'interaction_type': 'dismissed',
        }).execute()

        return {"success": True}

    except Exception as e:
        logger.error(f"Error dismissing insight: {e}")
        raise DatabaseError("Failed to dismiss insight", original_error=e)




@router.get("/insights/quick-stats")
async def get_quick_stats(user_id: str = Depends(get_current_user_id)):
    """
    Get aggregated quick stats for the insights dashboard.

    Returns:
        - energy: current, avg this week, trend
        - sleep: last night, avg this week, consistency
        - mood: dominant mood, volatility
        - streak: current streak, completion rate
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        two_weeks_ago = (now - timedelta(days=14)).isoformat()

        def get_mood_label(value: float) -> str:
            if value >= 4.5:
                return 'very_happy'
            elif value >= 3.5:
                return 'happy'
            elif value >= 2.5:
                return 'neutral'
            elif value >= 1.5:
                return 'sad'
            return 'very_sad'

        energy_stats = {
            'current': None,
            'avg_this_week': None,
            'avg_last_week': None,
            'best_time': None,
            'trend': 'stable'
        }

        try:
            current_energy = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'energy')
                .order('logged_at', desc=True)
                .limit(1)
                .execute()
            )
            if current_energy.data:
                energy_stats['current'] = float(current_energy.data[0]['value'])

            week_energy = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'energy')
                .gte('logged_at', week_ago)
                .execute()
            )
            if week_energy.data:
                values = [float(r['value']) for r in week_energy.data]
                energy_stats['avg_this_week'] = round(sum(values) / len(values), 1)

            last_week_energy = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'energy')
                .gte('logged_at', two_weeks_ago)
                .lt('logged_at', week_ago)
                .execute()
            )
            if last_week_energy.data:
                values = [float(r['value']) for r in last_week_energy.data]
                energy_stats['avg_last_week'] = round(sum(values) / len(values), 1)

            if energy_stats['avg_this_week'] and energy_stats['avg_last_week']:
                diff = energy_stats['avg_this_week'] - energy_stats['avg_last_week']
                if diff > 0.3:
                    energy_stats['trend'] = 'up'
                elif diff < -0.3:
                    energy_stats['trend'] = 'down'
        except Exception as e:
            logger.warning(f"Error calculating energy stats: {e}")

        sleep_stats = {
            'last_night': None,
            'avg_this_week': None,
            'consistency_score': None,
            'trend': 'stable'
        }

        try:
            last_sleep = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'sleep')
                .order('logged_at', desc=True)
                .limit(1)
                .execute()
            )
            if last_sleep.data:
                sleep_stats['last_night'] = float(last_sleep.data[0]['value'])

            week_sleep = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'sleep')
                .gte('logged_at', week_ago)
                .execute()
            )
            if week_sleep.data:
                values = [float(r['value']) for r in week_sleep.data]
                avg = sum(values) / len(values)
                sleep_stats['avg_this_week'] = round(avg, 1)

                if len(values) > 1:
                    mean = sum(values) / len(values)
                    variance = sum((x - mean) ** 2 for x in values) / len(values)
                    stddev = variance ** 0.5
                    consistency = max(0, min(100, int(100 - stddev * 20)))
                    sleep_stats['consistency_score'] = consistency
        except Exception as e:
            logger.warning(f"Error calculating sleep stats: {e}")

        mood_stats = {
            'dominant': None,
            'consistency': 'stable'
        }

        try:
            week_mood = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'mood')
                .gte('logged_at', week_ago)
                .execute()
            )
            if week_mood.data:
                values = [float(r['value']) for r in week_mood.data]
                from collections import Counter
                rounded = [round(v) for v in values]
                mode = Counter(rounded).most_common(1)[0][0]
                mood_stats['dominant'] = get_mood_label(mode)

                if len(values) > 1:
                    mean = sum(values) / len(values)
                    variance = sum((x - mean) ** 2 for x in values) / len(values)
                    stddev = variance ** 0.5
                    mood_stats['consistency'] = 'volatile' if stddev > 0.8 else 'stable'
        except Exception as e:
            logger.warning(f"Error calculating mood stats: {e}")

        streak_stats = {
            'current': 0,
            'completion_rate_this_week': 0
        }

        try:
            streak_response = (
                supabase.table('user_streaks')
                .select('current_streak')
                .eq('user_id', user_id)
                .limit(1)
                .execute()
            )
            if streak_response.data:
                streak_stats['current'] = streak_response.data[0].get('current_streak', 0)

            commitments = (
                supabase.table('commitments')
                .select('status')
                .eq('user_id', user_id)
                .gte('created_at', week_ago)
                .execute()
            )
            if commitments.data:
                total = len(commitments.data)
                completed = len([c for c in commitments.data if c['status'] == 'completed'])
                streak_stats['completion_rate_this_week'] = round(completed / total, 2) if total > 0 else 0
        except Exception as e:
            logger.warning(f"Error calculating streak stats: {e}")

        return {
            'energy': energy_stats,
            'sleep': sleep_stats,
            'mood': mood_stats,
            'streak': streak_stats
        }

    except Exception as e:
        logger.error(f"Error fetching quick stats: {e}")
        return {
            'energy': {'current': None, 'avg_this_week': None, 'avg_last_week': None, 'best_time': None, 'trend': 'stable'},
            'sleep': {'last_night': None, 'avg_this_week': None, 'consistency_score': None, 'trend': 'stable'},
            'mood': {'dominant': None, 'consistency': 'stable'},
            'streak': {'current': 0, 'completion_rate_this_week': 0}
        }


# ============================================
# METRICS ENDPOINTS (Personal Analytics)
# ============================================

VALID_METRIC_TYPES = ['energy', 'mood', 'sleep', 'stress', 'focus']


@router.post("/metrics/log")
async def log_metric(request: MetricLogRequest, user_id: str = Depends(get_current_user_id)):
    """Log a single metric (energy, mood, sleep, stress, focus)."""
    try:
        # Validate metric type
        if request.metric_type not in VALID_METRIC_TYPES:
            raise ValidationError(f"Invalid metric type. Must be one of: {VALID_METRIC_TYPES}")

        supabase = get_supabase_client()

        result = supabase.table('user_metrics').insert({
            'user_id': user_id,
            'metric_type': request.metric_type,
            'value': request.value,
            'notes': request.notes,
            'context': request.context,
            'logged_at': datetime.now(timezone.utc).isoformat()
        }).execute()

        if result.data:
            return {
                "success": True,
                "metric": result.data[0]
            }

        return {"success": True}

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error logging metric: {e}")
        raise DatabaseError("Failed to log metric", original_error=e)


@router.post("/metrics/batch")
async def log_batch_metrics(request: MetricBatchRequest, user_id: str = Depends(get_current_user_id)):
    """Log multiple metrics at once (batch check-in)."""
    try:
        if not request.metrics:
            raise ValidationError("At least one metric is required")

        # Validate all metric types
        for metric in request.metrics:
            if metric.metric_type not in VALID_METRIC_TYPES:
                raise ValidationError(f"Invalid metric type: {metric.metric_type}")

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        # Build batch insert data
        insert_data = []
        for metric in request.metrics:
            insert_data.append({
                'user_id': user_id,
                'metric_type': metric.metric_type,
                'value': metric.value,
                'notes': metric.notes,
                'context': metric.context,
                'logged_at': now
            })

        result = supabase.table('user_metrics').insert(insert_data).execute()

        return {
            "success": True,
            "metrics": result.data if result.data else [],
            "count": len(insert_data)
        }

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error batch logging metrics: {e}")
        raise DatabaseError("Failed to batch log metrics", original_error=e)


@router.get("/metrics/latest")
async def get_latest_metrics(user_id: str = Depends(get_current_user_id)):
    """Get the most recent value for each metric type."""
    try:
        supabase = get_supabase_client()

        # Query latest metric for each type
        latest = {}
        for metric_type in VALID_METRIC_TYPES:
            result = (
                supabase.table('user_metrics')
                .select('value,logged_at,context')
                .eq('user_id', user_id)
                .eq('metric_type', metric_type)
                .order('logged_at', desc=True)
                .limit(1)
                .execute()
            )

            if result.data and len(result.data) > 0:
                row = result.data[0]
                latest[metric_type] = {
                    'value': float(row['value']),
                    'logged_at': row['logged_at'],
                    'context': row.get('context')
                }

        return latest

    except Exception as e:
        logger.error(f"Error fetching latest metrics: {e}")
        raise DatabaseError("Failed to fetch latest metrics", original_error=e)


@router.get("/insights/quick-stats")
async def get_quick_stats(user_id: str = Depends(get_current_user_id)):
    """
    Get aggregated quick stats for the insights dashboard.

    Returns:
        - energy: current, avg this week, trend
        - sleep: last night, avg this week, consistency
        - mood: dominant mood, volatility
        - streak: current streak, completion rate
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        two_weeks_ago = (now - timedelta(days=14)).isoformat()

        # Helper to get mood label
        def get_mood_label(value: float) -> str:
            if value >= 4.5:
                return 'very_happy'
            elif value >= 3.5:
                return 'happy'
            elif value >= 2.5:
                return 'neutral'
            elif value >= 1.5:
                return 'sad'
            return 'very_sad'

        # Get energy stats
        energy_stats = {
            'current': None,
            'avg_this_week': None,
            'avg_last_week': None,
            'best_time': None,
            'trend': 'stable'
        }

        try:
            # Current energy (most recent)
            current_energy = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'energy')
                .order('logged_at', desc=True)
                .limit(1)
                .execute()
            )
            if current_energy.data:
                energy_stats['current'] = float(current_energy.data[0]['value'])

            # This week's energy average
            week_energy = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'energy')
                .gte('logged_at', week_ago)
                .execute()
            )
            if week_energy.data:
                values = [float(r['value']) for r in week_energy.data]
                energy_stats['avg_this_week'] = round(sum(values) / len(values), 1)

            # Last week's energy average
            last_week_energy = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'energy')
                .gte('logged_at', two_weeks_ago)
                .lt('logged_at', week_ago)
                .execute()
            )
            if last_week_energy.data:
                values = [float(r['value']) for r in last_week_energy.data]
                energy_stats['avg_last_week'] = round(sum(values) / len(values), 1)

            # Calculate trend
            if energy_stats['avg_this_week'] and energy_stats['avg_last_week']:
                diff = energy_stats['avg_this_week'] - energy_stats['avg_last_week']
                if diff > 0.3:
                    energy_stats['trend'] = 'up'
                elif diff < -0.3:
                    energy_stats['trend'] = 'down'

        except Exception as e:
            logger.warning(f"Error calculating energy stats: {e}")

        # Get sleep stats
        sleep_stats = {
            'last_night': None,
            'avg_this_week': None,
            'consistency_score': None,
            'trend': 'stable'
        }

        try:
            # Last night's sleep
            last_sleep = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'sleep')
                .order('logged_at', desc=True)
                .limit(1)
                .execute()
            )
            if last_sleep.data:
                sleep_stats['last_night'] = float(last_sleep.data[0]['value'])

            # This week's sleep
            week_sleep = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'sleep')
                .gte('logged_at', week_ago)
                .execute()
            )
            if week_sleep.data:
                values = [float(r['value']) for r in week_sleep.data]
                avg = sum(values) / len(values)
                sleep_stats['avg_this_week'] = round(avg, 1)

                # Calculate consistency (100 - stddev * 20, clamped to 0-100)
                if len(values) > 1:
                    mean = sum(values) / len(values)
                    variance = sum((x - mean) ** 2 for x in values) / len(values)
                    stddev = variance ** 0.5
                    consistency = max(0, min(100, int(100 - stddev * 20)))
                    sleep_stats['consistency_score'] = consistency

        except Exception as e:
            logger.warning(f"Error calculating sleep stats: {e}")

        # Get mood stats
        mood_stats = {
            'dominant': None,
            'consistency': 'stable'
        }

        try:
            week_mood = (
                supabase.table('user_metrics')
                .select('value')
                .eq('user_id', user_id)
                .eq('metric_type', 'mood')
                .gte('logged_at', week_ago)
                .execute()
            )
            if week_mood.data:
                values = [float(r['value']) for r in week_mood.data]

                # Dominant mood (mode of rounded values)
                rounded = [round(v) for v in values]
                from collections import Counter
                mode = Counter(rounded).most_common(1)[0][0]
                mood_stats['dominant'] = get_mood_label(mode)

                # Volatility check
                if len(values) > 1:
                    mean = sum(values) / len(values)
                    variance = sum((x - mean) ** 2 for x in values) / len(values)
                    stddev = variance ** 0.5
                    mood_stats['consistency'] = 'volatile' if stddev > 0.8 else 'stable'

        except Exception as e:
            logger.warning(f"Error calculating mood stats: {e}")

        # Get streak stats
        streak_stats = {
            'current': 0,
            'completion_rate_this_week': 0
        }

        try:
            streak_response = (
                supabase.table('user_streaks')
                .select('current_streak')
                .eq('user_id', user_id)
                .limit(1)
                .execute()
            )
            if streak_response.data:
                streak_stats['current'] = streak_response.data[0].get('current_streak', 0)

            # Get commitment completion rate this week
            commitments = (
                supabase.table('commitments')
                .select('status')
                .eq('user_id', user_id)
                .gte('created_at', week_ago)
                .execute()
            )
            if commitments.data:
                total = len(commitments.data)
                completed = len([c for c in commitments.data if c['status'] == 'completed'])
                streak_stats['completion_rate_this_week'] = round(completed / total, 2) if total > 0 else 0

        except Exception as e:
            logger.warning(f"Error calculating streak stats: {e}")

        return {
            'energy': energy_stats,
            'sleep': sleep_stats,
            'mood': mood_stats,
            'streak': streak_stats
        }

    except Exception as e:
        logger.error(f"Error fetching quick stats: {e}")
        # Return empty stats on error - don't crash
        return {
            'energy': {'current': None, 'avg_this_week': None, 'avg_last_week': None, 'best_time': None, 'trend': 'stable'},
            'sleep': {'last_night': None, 'avg_this_week': None, 'consistency_score': None, 'trend': 'stable'},
            'mood': {'dominant': None, 'consistency': 'stable'},
            'streak': {'current': 0, 'completion_rate_this_week': 0}
        }


# ============================================
# COMMITMENT PATTERN INSIGHTS ENDPOINTS
# ============================================

class InsightReactionRequest(BaseModel):
    helpful: bool


@router.get("/insights/commitment-patterns")
async def get_commitment_insights(user_id: str = Depends(get_current_user_id)):
    """
    Get commitment-pattern-focused insights with AI coach interpretation.

    Returns:
        - coach_summary: Overall coach summary (if enough data)
        - patterns: List of pattern insights (max 5)
        - has_enough_data: Whether user has enough data for insights
        - days_until_enough_data: Days needed if not enough data
    """
    try:
        from backend.services.commitment_insights_engine import commitment_insights_engine

        result = await commitment_insights_engine.get_active_insights(user_id)
        return result

    except Exception as e:
        logger.error(f"Error fetching commitment insights: {e}")
        # Return graceful fallback - never crash
        return {
            "coach_summary": None,
            "patterns": [],
            "has_enough_data": False,
            "days_until_enough_data": 3
        }



# ============================================
# HEALTH PATTERN INSIGHTS ENDPOINTS
# ============================================

@router.get("/insights/health-patterns")
async def get_health_insights(user_id: str = Depends(get_current_user_id)):
    """
    Get health-first insights derived from sleep/activity data.
    """
    try:
        from backend.services.health_insights_engine import health_insights_engine

        result = await health_insights_engine.get_active_insights(user_id)
        return result

    except Exception as e:
        logger.error(f"Error fetching health insights: {e}")
        return {
            "coach_summary": None,
            "patterns": [],
            "has_enough_data": False,
            "days_until_enough_data": 3
        }


@router.post("/insights/{insight_id}/reaction")
async def record_insight_reaction(
    insight_id: str,
    request: InsightReactionRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Record user reaction (helpful/not helpful) to an insight."""
    try:
        from backend.services.commitment_insights_engine import commitment_insights_engine

        success = await commitment_insights_engine.mark_insight_reaction(
            insight_id=insight_id,
            user_id=user_id,
            helpful=request.helpful
        )

        return {"success": success}

    except Exception as e:
        logger.error(f"Error recording insight reaction: {e}")
        raise DatabaseError("Failed to record reaction", original_error=e)


# ============================================
# COMMITMENTS ENDPOINTS
# ============================================

@router.get("/commitments")
async def get_commitments(user_id: str = Depends(get_current_user_id)):
    """Get active commitments."""
    try:
        response = get_supabase_client().table('commitments').select('*').eq(
            'user_id', user_id
        ).eq('status', 'active').order('created_at', desc=True).execute()
        
        commitments = []
        if response.data:
            for c in response.data:
                commitments.append({
                    "id": c['id'],
                    "text": c['commitment_text'],
                    "dueDate": c.get('due_date'),
                    "priority": c.get('priority', 'medium'),
                    "createdAt": c['created_at']
                })
        
        return commitments
        
    except Exception as e:
        logger.error(f"Error fetching commitments: {e}")
        raise DatabaseError("Failed to fetch commitments", original_error=e)


@router.post("/commitments/{commitment_id}/check-in")
async def check_in_commitment(commitment_id: str, user_id: str = Depends(get_current_user_id)):
    """Check in on a commitment (mark as completed)."""
    try:
        get_supabase_client().table('commitments').update({
            'status': 'completed',
            'completed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', commitment_id).eq('user_id', user_id).execute()
        
        # Update streak (simplified schema)
        try:
            result = get_supabase_client().rpc('update_user_streak', {
                'p_user_id': user_id,
                'p_user_timezone': 'UTC'
            }).execute()
            logger.info(f"Streak update RPC result for {user_id}: {result.data}")
        except Exception as streak_error:
            logger.error(f"Could not update streak via RPC for {user_id}: {streak_error}")
            # Try manual update as fallback
            try:
                today = date.today().isoformat()
                supabase = get_supabase_client()
                # Check if streak record exists
                existing = supabase.table('user_streaks').select('*').eq('user_id', user_id).execute()
                if existing.data:
                    # Update existing record
                    supabase.table('user_streaks').update({
                        'current_streak': 1,
                        'last_activity_date': today
                    }).eq('user_id', user_id).execute()
                    logger.info(f"Manual streak update for {user_id}")
                else:
                    # Insert new record
                    supabase.table('user_streaks').insert({
                        'user_id': user_id,
                        'current_streak': 1,
                        'longest_streak': 1,
                        'last_activity_date': today
                    }).execute()
                    logger.info(f"Manual streak insert for {user_id}")
            except Exception as manual_error:
                logger.error(f"Manual streak update also failed for {user_id}: {manual_error}")
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error checking in commitment: {e}")
        raise DatabaseError("Failed to check in", original_error=e)


# ============================================
# COACH ENDPOINTS
# ============================================

@router.get("/coach/last-message")
async def get_last_coach_message(user_id: str = Depends(get_current_user_id)):
    """Get the last message from the coach."""
    try:
        response = (
            get_supabase_client().table('messages')
            .select('*')
            .eq('userid', user_id)
            .or_('direction.eq.outgoing,sender_type.eq.gpt')
            .order('created_at', desc=True)
            .limit(1)
            .execute()
        )

        if response.data:
            msg = response.data[0]
            direction = msg.get('direction') or (
                'incoming' if msg.get('sender_type') == 'user'
                else 'outgoing' if msg.get('sender_type') == 'gpt'
                else None
            )
            if direction != 'outgoing':
                return None
            
            get_supabase_client().table('messages').update({
                'read_in_app': True,
                'read_at': datetime.now(timezone.utc).isoformat()
            }).eq('chat_id', msg['chat_id']).execute()
            
            return {
                "id": msg['id'],
                "text": msg['message_text'],
                "timestamp": msg['created_at'],
                "read": True
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching coach message: {e}")
        raise DatabaseError("Failed to fetch message", original_error=e)


@router.get("/coach/messages")
async def get_coach_messages(
    user_id: str = Depends(get_current_user_id),
    limit: int = 20,
    offset: int = 0
):
    """Get recent coach messages."""
    try:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        response = (
            get_supabase_client()
            .table('messages')
            .select('*')
            .eq('userid', user_id)
            .order('created_at', desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        
        messages = []
        if response.data:
            for msg in response.data:
                direction = msg.get('direction') or (
                    'incoming' if msg.get('sender_type') == 'user'
                    else 'outgoing' if msg.get('sender_type') == 'gpt'
                    else None
                )
                messages.append({
                    "id": msg['chat_id'],                # Changed from 'id' to 'chat_id'
                    "text": msg.get('content', msg.get('message_text', '')),  # Support both new and old schema
                    "direction": direction,
                    "timestamp": msg['created_at'],
                    "read": msg.get('read_in_app', False)
                })
        
        return messages
        
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        raise DatabaseError("Failed to fetch messages", original_error=e)


# ============================================
# PROFILE ENDPOINTS
# ============================================

@router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Get user profile."""
    try:
        response = get_supabase_client().table('users').select('*').eq('id', user_id).maybe_single().execute()
        
        if response and response.data:
            user = response.data
            
            # Get phone number if exists
            phone_response = get_supabase_client().table('user_phone_numbers').select('*').eq(
                'user_id', user_id
            ).eq('is_primary', True).limit(1).execute()
            
            phone_number = None
            phone_verified = False
            if phone_response.data and len(phone_response.data) > 0:
                phone_number = phone_response.data[0].get('phone_number')
                phone_verified = phone_response.data[0].get('verified', False)
            
            return {
                "id": user['id'],
                "email": user.get('email'),
                "fullName": user.get('full_name'),
                "avatarUrl": user.get('avatar_url'),
                "timezone": user.get('timezone', 'UTC'),
                "onboardingCompleted": user.get('onboarding_completed', False),
                "phoneNumber": phone_number,
                "phoneVerified": phone_verified,
                "createdAt": user['created_at']
            }
        
        # If user doesn't exist in database, return default profile data
        logger.info(f"User {user_id} not found in database, returning default profile")
        return {
            "id": user_id,
            "email": "user@coresense.app",
            "fullName": "CoreSense User",
            "avatarUrl": None,
            "timezone": "UTC",
            "onboardingCompleted": True,
            "phoneNumber": None,
            "phoneVerified": False,
            "createdAt": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        # Return default profile data instead of error
        return {
            "id": user_id,
            "email": "user@coresense.app",
            "fullName": "CoreSense User",
            "avatarUrl": None,
            "timezone": "UTC",
            "onboardingCompleted": True,
            "phoneNumber": None,
            "phoneVerified": False,
            "createdAt": datetime.now().isoformat()
        }


@router.put("/profile")
async def update_profile(request: ProfileUpdateRequest, user_id: str = Depends(get_current_user_id)):
    """Update user profile."""
    try:
        updates = {}
        if request.full_name is not None:
            updates['full_name'] = request.full_name
        if request.username is not None:
            updates['username'] = request.username
        if request.timezone is not None:
            updates['timezone'] = request.timezone

        if updates:
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()
            get_supabase_client().table('users').update(updates).eq('id', user_id).execute()
        
        # Handle phone number update separately
        if request.phone_number is not None:
            normalized = ''.join(c for c in request.phone_number if c.isdigit() or c == '+')
            if not normalized.startswith('+'):
                normalized = '+' + normalized
            
            supabase = get_supabase_client()
            existing = supabase.table('user_phone_numbers').select('id').eq(
                'user_id', user_id
            ).eq('is_primary', True).limit(1).execute()
            
            if existing.data:
                supabase.table('user_phone_numbers').update({
                    'phone_number': request.phone_number,
                    'phone_normalized': normalized,
                    'verified': False,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq('id', existing.data[0]['id']).execute()
            else:
                supabase.table('user_phone_numbers').insert({
                    'user_id': user_id,
                    'phone_number': request.phone_number,
                    'phone_normalized': normalized,
                    'is_primary': True,
                    'verified': False,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }).execute()
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise DatabaseError("Failed to update profile", original_error=e)


@router.get("/preferences")
async def get_preferences(user_id: str = Depends(get_current_user_id)):
    """Get user preferences."""
    try:
        response = get_supabase_client().table('user_preferences').select('*').eq(
            'user_id', user_id
        ).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            prefs = response.data[0]
            return {
                "messagingStyle": prefs.get('messaging_style', 'balanced'),
                "messagingFrequency": prefs.get('messaging_frequency', 3),
                "quietHoursEnabled": prefs.get('quiet_hours_enabled', False),
                "quietHoursStart": prefs.get('quiet_hours_start', '22:00'),
                "quietHoursEnd": prefs.get('quiet_hours_end', '07:00'),
                "accountabilityLevel": prefs.get('accountability_level', 5),
                "goals": prefs.get('goals', []),
                "healthkitEnabled": prefs.get('healthkit_enabled', False)
            }
        
        # Return defaults if no preferences exist
        return {
            "messagingStyle": "balanced",
            "messagingFrequency": 3,
            "quietHoursEnabled": False,
            "quietHoursStart": "22:00",
            "quietHoursEnd": "07:00",
            "accountabilityLevel": 5,
            "goals": [],
            "healthkitEnabled": False
        }
        
    except Exception as e:
        logger.error(f"Error fetching preferences: {e}")
        raise DatabaseError("Failed to fetch preferences", original_error=e)


@router.put("/preferences")
async def update_preferences(request: PreferencesUpdateRequest, user_id: str = Depends(get_current_user_id)):
    """Update user preferences."""
    try:
        updates = {'updated_at': datetime.now(timezone.utc).isoformat()}
        
        if request.messaging_style is not None:
            updates['messaging_style'] = request.messaging_style
        if request.messaging_frequency is not None:
            updates['messaging_frequency'] = request.messaging_frequency
        if request.quiet_hours_enabled is not None:
            updates['quiet_hours_enabled'] = request.quiet_hours_enabled
        if request.quiet_hours_start is not None:
            updates['quiet_hours_start'] = request.quiet_hours_start
        if request.quiet_hours_end is not None:
            updates['quiet_hours_end'] = request.quiet_hours_end
        if request.accountability_level is not None:
            updates['accountability_level'] = request.accountability_level
        if request.goals is not None:
            updates['goals'] = request.goals
        if request.healthkit_enabled is not None:
            updates['healthkit_enabled'] = request.healthkit_enabled
        
        # Upsert preferences
        get_supabase_client().table('user_preferences').upsert({
            'user_id': user_id,
            **updates
        }).execute()
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error updating preferences: {e}")
        raise DatabaseError("Failed to update preferences", original_error=e)


# ============================================
# HEALTH DATA ENDPOINTS
# ============================================

@router.post("/health/sync")
async def sync_health_data(
    request: HealthSyncRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Sync health data from mobile app."""
    try:
        if not request.metrics:
            return {"success": True, "inserted": 0}

        # De-dupe metrics by metric_type + recorded_at
        merged = {}
        for metric in request.metrics:
            key = f"{metric.metric_type}:{metric.recorded_at.isoformat()}"
            if key not in merged:
                merged[key] = metric
                continue
            existing = merged[key]
            if metric.metric_type == "steps":
                existing.value += metric.value
            elif metric.metric_type == "sleep_duration":
                existing.value = max(existing.value, metric.value)
            else:
                merged[key] = metric

        payload = []
        for metric in merged.values():
            payload.append({
                "user_id": user_id,
                "metric_type": metric.metric_type,
                "value": metric.value,
                "unit": metric.unit,
                "recorded_at": metric.recorded_at.isoformat(),
                "source": metric.source,
                "metadata": metric.metadata or {},
            })

        supabase = get_supabase_client()
        response = supabase.table("health_metrics").upsert(
            payload, on_conflict="user_id,metric_type,recorded_at"
        ).execute()

        # Daily aggregation now happens via health_metrics_daily database view
        # No need to maintain separate user_health_data table

        return {"success": True, "inserted": len(payload)}

    except Exception as e:
        logger.error(f"Error syncing health data: {e}")
        raise DatabaseError("Failed to sync health data", original_error=e)


@router.get("/health/summary")
async def get_health_summary(user_id: str = Depends(get_current_user_id)):
    """Get health data summary."""
    try:
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        
        # Get steps data
        steps_response = get_supabase_client().table('health_metrics').select('*').eq(
            'user_id', user_id
        ).eq('metric_type', 'steps').gte('recorded_at', week_ago).execute()
        
        # Get sleep data
        sleep_response = get_supabase_client().table('health_metrics').select('*').eq(
            'user_id', user_id
        ).eq('metric_type', 'sleep_duration').gte('recorded_at', week_ago).execute()
        
        steps_data = steps_response.data or []
        sleep_data = sleep_response.data or []
        
        # Calculate averages
        avg_steps = sum(s['value'] for s in steps_data) / max(len(steps_data), 1) if steps_data else 0
        avg_sleep = sum(s['value'] for s in sleep_data) / max(len(sleep_data), 1) if sleep_data else 0
        
        return {
            "weeklySteps": [{"date": s['recorded_at'], "value": s['value']} for s in steps_data],
            "weeklySleep": [{"date": s['recorded_at'], "value": s['value']} for s in sleep_data],
            "averages": {
                "steps": round(avg_steps),
                "sleep": round(avg_sleep, 1)
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching health summary: {e}")
        raise DatabaseError("Failed to fetch health summary", original_error=e)


# ============================================
# STREAKS ENDPOINTS (Simplified Schema)
# ============================================

class RecordStreakRequest(BaseModel):
    timezone: str = "UTC"


@router.get("/streak")
async def get_streak(user_id: str = Depends(get_current_user_id)):
    """Get user's current streak (simplified schema only)."""
    try:
        response = (
            get_supabase_client()
            .table('user_streaks')
            .select('current_streak,longest_streak,last_activity_date,user_timezone')
            .eq('user_id', user_id)
            .limit(1)
            .execute()
        )
        
        if response.data and len(response.data) > 0:
            s = response.data[0]
            return {
                "currentStreak": s.get('current_streak', 0),
                "longestStreak": s.get('longest_streak', 0),
                "lastActivityDate": s.get('last_activity_date'),
                "userTimezone": s.get('user_timezone', 'UTC')
            }
        
        # No streak found - return defaults
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastActivityDate": None,
            "userTimezone": "UTC"
        }
        
    except Exception as e:
        logger.error(f"Error fetching streak: {e}")
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastActivityDate": None,
            "userTimezone": "UTC"
        }


@router.post("/streak/record")
async def record_streak(
    request: RecordStreakRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Record a streak activity (simplified schema only)."""
    try:
        # Try the new RPC first
        try:
            result = (
                get_supabase_client()
                .rpc('update_user_streak', {
                    'p_user_id': user_id,
                    'p_user_timezone': request.timezone
                })
                .execute()
            )
            
            if result.data:
                return {
                    "success": True,
                    "currentStreak": result.data.get('current_streak', 0),
                    "longestStreak": result.data.get('longest_streak', 0),
                    "lastActivityDate": result.data.get('last_activity_date'),
                    "userTimezone": result.data.get('user_timezone', request.timezone)
                }
        except Exception as rpc_error:
            logger.warning(f"Streak RPC not available, using manual update: {rpc_error}")
        
        # Manual streak calculation
        supabase = get_supabase_client()
        today = date.today()
        
        response = (
            supabase.table('user_streaks')
            .select('*')
            .eq('user_id', user_id)
            .execute()
        )
        
        if response.data and len(response.data) > 0:
            current = response.data[0]
            last_date = current.get('last_activity_date')
            
            if last_date == today.isoformat():
                return {
                    "success": True,
                    "currentStreak": current.get('current_streak', 0),
                    "longestStreak": current.get('longest_streak', 0),
                    "lastActivityDate": last_date,
                    "userTimezone": request.timezone
                }
            elif last_date == (today - timedelta(days=1)).isoformat():
                new_streak = current.get('current_streak', 0) + 1
                new_longest = max(current.get('longest_streak', 0), new_streak)
                
                supabase.table('user_streaks').update({
                    'current_streak': new_streak,
                    'longest_streak': new_longest,
                    'last_activity_date': today.isoformat(),
                    'user_timezone': request.timezone
                }).eq('user_id', user_id).execute()
                
                return {
                    "success": True,
                    "currentStreak": new_streak,
                    "longestStreak": new_longest,
                    "lastActivityDate": today.isoformat(),
                    "userTimezone": request.timezone
                }
            else:
                supabase.table('user_streaks').update({
                    'current_streak': 1,
                    'last_activity_date': today.isoformat(),
                    'user_timezone': request.timezone
                }).eq('user_id', user_id).execute()
                
                return {
                    "success": True,
                    "currentStreak": 1,
                    "longestStreak": current.get('longest_streak', 0),
                    "lastActivityDate": today.isoformat(),
                    "userTimezone": request.timezone
                }
        else:
            supabase.table('user_streaks').insert({
                'user_id': user_id,
                'current_streak': 1,
                'longest_streak': 1,
                'last_activity_date': today.isoformat(),
                'user_timezone': request.timezone
            }).execute()
            
            return {
                "success": True,
                "currentStreak": 1,
                "longestStreak": 1,
                "lastActivityDate": today.isoformat(),
                "userTimezone": request.timezone
            }
        
    except Exception as e:
        logger.error(f"Error recording streak: {e}")
        return {
            "success": False,
            "currentStreak": 0,
            "longestStreak": 0,
            "lastActivityDate": None,
            "userTimezone": request.timezone,
            "error": str(e)
        }


@router.get("/streaks")
async def get_streaks_legacy(user_id: str = Depends(get_current_user_id)):
    """Get user streak (simplified schema - single record per user)."""
    try:
        response = (
            get_supabase_client()
            .table('user_streaks')
            .select('current_streak,longest_streak,last_activity_date,user_timezone')
            .eq('user_id', user_id)
            .limit(1)
            .execute()
        )
        
        streaks = {}
        if response.data and len(response.data) > 0:
            s = response.data[0]
            streaks['check_in'] = {
                "current": s.get('current_streak', 0),
                "longest": s.get('longest_streak', 0),
                "lastActivity": s.get('last_activity_date'),
                "userTimezone": s.get('user_timezone', 'UTC')
            }
        
        return streaks
        
    except Exception as e:
        logger.error(f"Error fetching streaks: {e}")
        return {}


# ============================================
# ENGAGEMENT ENDPOINTS
# ============================================

class DidItRequest(BaseModel):
    """Request for recording a completed action."""
    timezone: str = "UTC"


@router.post("/engagement/did-it")
async def did_it(
    request: DidItRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Record a 'did it' action and update streak."""
    try:
        supabase = get_supabase_client()
        today = date.today().isoformat()
        
        # Check if streak record exists
        existing = supabase.table('user_streaks').select('*').eq('user_id', user_id).execute()
        
        if existing.data and len(existing.data) > 0:
            current = existing.data[0]
            last_date = current.get('last_activity_date')
            
            if last_date == today:
                # Already recorded today
                return {
                    "success": True,
                    "newTotal": current.get('current_streak', 0),
                    "streak": current.get('current_streak', 0)
                }
            elif last_date == (today - timedelta(days=1)).isoformat():
                # Consecutive day - increment
                new_streak = current.get('current_streak', 0) + 1
                new_longest = max(current.get('longest_streak', 0), new_streak)
                
                supabase.table('user_streaks').update({
                    'current_streak': new_streak,
                    'longest_streak': new_longest,
                    'last_activity_date': today,
                    'user_timezone': request.timezone
                }).eq('user_id', user_id).execute()
                
                return {
                    "success": True,
                    "newTotal": new_streak,
                    "streak": new_streak
                }
            else:
                # Streak broken - reset to 1
                supabase.table('user_streaks').update({
                    'current_streak': 1,
                    'longest_streak': max(current.get('longest_streak', 0), 1),
                    'last_activity_date': today,
                    'user_timezone': request.timezone
                }).eq('user_id', user_id).execute()
                
                return {
                    "success": True,
                    "newTotal": 1,
                    "streak": 1
                }
        else:
            # No streak record - create new
            supabase.table('user_streaks').insert({
                'user_id': user_id,
                'current_streak': 1,
                'longest_streak': 1,
                'last_activity_date': today,
                'user_timezone': request.timezone
            }).execute()
            
            return {
                "success": True,
                "newTotal": 1,
                "streak": 1
            }
            
    except Exception as e:
        logger.error(f"Error in did-it for {user_id}: {e}")
        return {
            "success": False,
            "newTotal": 0,
            "streak": 0,
            "error": str(e)
        }

class FeedbackRequest(BaseModel):
    category: str
    message: str
    userEmail: Optional[str] = None
    userName: Optional[str] = None
    timestamp: Optional[str] = None
    platform: Optional[str] = None


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Submit user feedback - stores in database and can be emailed."""
    try:
        # Store feedback in database
        feedback_data = {
            'category': request.category,
            'message': request.message,
            'user_email': request.userEmail,
            'user_name': request.userName,
            'platform': request.platform,
            'created_at': request.timestamp or datetime.now(timezone.utc).isoformat()
        }
        
        # Try to store in Supabase feedback table
        try:
            get_supabase_client().table('app_feedback').insert(feedback_data).execute()
        except Exception as db_error:
            # Table might not exist, just log the feedback
            logger.info(f"Feedback received: {feedback_data}")
        
        # Log the feedback for visibility
        logger.info(f"User feedback: [{request.category}] from {request.userEmail}: {request.message}")
        
        return {"success": True, "message": "Feedback received"}
        
    except Exception as e:
        logger.error(f"Error processing feedback: {e}")
        # Don't fail - feedback should always appear to succeed to user
        return {"success": True, "message": "Feedback recorded"}


# ============================================
# USER INITIALIZATION ENDPOINT
# ============================================

class UserInitRequest(BaseModel):
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None


@router.post("/user/initialize")
async def initialize_user(request: UserInitRequest, authenticated_user_id: str = Depends(get_current_user_id)):
    """Initialize user data for new signups."""
    try:
        # Ensure the authenticated user matches the request
        if request.user_id != authenticated_user_id:
            from backend.utils.exceptions import AuthorizationError
            raise AuthorizationError("Cannot initialize data for other users")
        
        logger.info(f"Initializing user data for: {request.user_id}")
        
        # Initialize user data
        result = initialize_new_user(
            user_id=request.user_id,
            user_email=request.email,
            full_name=request.full_name
        )
        
        if result['success']:
            logger.info(f"✅ User initialization successful for {request.user_id}")
            return {
                "success": True,
                "message": "User data initialized successfully",
                "initialized": result['initialized'],
                "errors": result['errors']
            }
        else:
            logger.warning(f"⚠️ User initialization completed with errors for {request.user_id}")
            return {
                "success": False,
                "message": "User initialization completed with errors",
                "initialized": result['initialized'],
                "errors": result['errors']
            }
            
    except Exception as e:
        logger.error(f"Error initializing user {request.user_id}: {e}")
        raise DatabaseError("Failed to initialize user", original_error=e)
