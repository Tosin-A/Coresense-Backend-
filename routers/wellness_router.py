"""
Wellness Router
API endpoints for wellness insights, goals, and health logging
"""

from fastapi import APIRouter, Depends
from datetime import date, datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import logging

from backend.database.supabase_client import get_supabase_client
from backend.middleware.auth_helper import get_current_user_id
from backend.services.wellness_analytics_service import wellness_analytics_service
from backend.services.insight_generation_service import insight_generation_service
from backend.services.goal_management_service import goal_management_service
from backend.utils.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/wellness", tags=["wellness"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ManualHealthLogRequest(BaseModel):
    log_type: str  # 'mood', 'stress', 'water', 'nutrition'
    value: Optional[float] = None
    text_value: Optional[str] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


class GoalCreateRequest(BaseModel):
    goal_type: str
    target_value: float
    unit: Optional[str] = None
    period: str = "daily"
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class GoalUpdateRequest(BaseModel):
    target_value: Optional[float] = None
    status: Optional[str] = None
    end_date: Optional[str] = None


# ============================================
# WELLNESS SCORE ENDPOINTS
# ============================================

@router.get("/score")
async def get_wellness_score(
    target_date: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Get wellness score for user"""
    try:
        score_date = date.today()
        if target_date:
            score_date = date.fromisoformat(target_date)
        
        score = await wellness_analytics_service.calculate_wellness_score(user_id, score_date)
        
        return {
            "overall_score": score.overall,
            "sleep_score": score.sleep,
            "activity_score": score.activity,
            "nutrition_score": score.nutrition,
            "mental_wellbeing_score": score.mental,
            "hydration_score": score.hydration,
            "trend": score.trend,
            "date": score.date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting wellness score: {e}")
        raise DatabaseError("Failed to get wellness score", original_error=e)


@router.get("/score/history")
async def get_wellness_score_history(
    days: int = 7,
    user_id: str = Depends(get_current_user_id)
):
    """Get wellness score history"""
    try:
        end_date = date.today()
        start_date = date.today() - timedelta(days=days)
        
        response = get_supabase_client().table('wellness_scores').select('*').eq(
            'user_id', user_id
        ).gte('score_date', start_date.isoformat()).lte(
            'score_date', end_date.isoformat()
        ).order('score_date', desc=True).execute()
        
        scores = []
        if response.data:
            for s in response.data:
                scores.append({
                    "overall_score": s['overall_score'],
                    "sleep_score": s.get('sleep_score'),
                    "activity_score": s.get('activity_score'),
                    "nutrition_score": s.get('nutrition_score'),
                    "mental_wellbeing_score": s.get('mental_wellbeing_score'),
                    "hydration_score": s.get('hydration_score'),
                    "trend": s.get('trend'),
                    "date": s['score_date']
                })
        
        return {"scores": scores}
        
    except Exception as e:
        logger.error(f"Error getting score history: {e}")
        raise DatabaseError("Failed to get score history", original_error=e)


# ============================================
# INSIGHTS ENDPOINTS
# ============================================

@router.get("/insights")
async def get_wellness_insights(
    period: str = "weekly",
    user_id: str = Depends(get_current_user_id)
):
    """Get generated wellness insights"""
    try:
        insights = await insight_generation_service.generate_insights(user_id, period)
        
        return {"insights": insights}
        
    except Exception as e:
        logger.error(f"Error getting insights: {e}")
        raise DatabaseError("Failed to get insights", original_error=e)


# ============================================
# MANUAL HEALTH LOGGING ENDPOINTS
# ============================================

@router.post("/logs")
async def log_manual_health_data(
    log_data: ManualHealthLogRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Log manual health data (mood, stress, water, nutrition)"""
    try:
        if log_data.log_type not in ['mood', 'stress', 'water', 'nutrition', 'custom']:
            raise ValidationError("Invalid log_type")
        
        log_entry = {
            'user_id': user_id,
            'log_type': log_data.log_type,
            'logged_at': datetime.now().isoformat()
        }
        
        if log_data.value is not None:
            log_entry['value'] = log_data.value
        if log_data.text_value:
            log_entry['text_value'] = log_data.text_value
        if log_data.unit:
            log_entry['unit'] = log_data.unit
        if log_data.notes:
            log_entry['notes'] = log_data.notes
        
        response = get_supabase_client().table('manual_health_logs').insert(log_entry).execute()
        
        if response.data:
            return {
                "success": True,
                "log": response.data[0]
            }
        
        return {"success": False}
        
    except Exception as e:
        logger.error(f"Error logging health data: {e}")
        raise DatabaseError("Failed to log health data", original_error=e)


@router.get("/logs")
async def get_manual_health_logs(
    log_type: Optional[str] = None,
    days: int = 7,
    user_id: str = Depends(get_current_user_id)
):
    """Get manual health logs"""
    try:
        start_date = datetime.now() - timedelta(days=days)
        
        query = get_supabase_client().table('manual_health_logs').select('*').eq(
            'user_id', user_id
        ).gte('logged_at', start_date.isoformat())
        
        if log_type:
            query = query.eq('log_type', log_type)
        
        response = query.order('logged_at', desc=True).execute()
        
        return {"logs": response.data or []}
        
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise DatabaseError("Failed to get logs", original_error=e)


# ============================================
# GOALS ENDPOINTS
# ============================================

@router.post("/goals")
async def create_goal(
    goal_data: GoalCreateRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Create a new wellness goal"""
    try:
        goal = await goal_management_service.create_goal(user_id, goal_data.dict())
        return {"success": True, "goal": goal}
        
    except Exception as e:
        logger.error(f"Error creating goal: {e}")
        raise DatabaseError("Failed to create goal", original_error=e)


@router.get("/goals")
async def get_goals(
    status: Optional[str] = "active",
    user_id: str = Depends(get_current_user_id)
):
    """Get user's wellness goals"""
    try:
        goals = await goal_management_service.get_goals(user_id, status)
        return {"goals": goals}
        
    except Exception as e:
        logger.error(f"Error getting goals: {e}")
        raise DatabaseError("Failed to get goals", original_error=e)


@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    updates: GoalUpdateRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Update a wellness goal"""
    try:
        update_dict = {k: v for k, v in updates.dict().items() if v is not None}
        goal = await goal_management_service.update_goal(goal_id, user_id, update_dict)
        return {"success": True, "goal": goal}
        
    except Exception as e:
        logger.error(f"Error updating goal: {e}")
        raise DatabaseError("Failed to update goal", original_error=e)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Delete a wellness goal"""
    try:
        success = await goal_management_service.delete_goal(goal_id, user_id)
        return {"success": success}
        
    except Exception as e:
        logger.error(f"Error deleting goal: {e}")
        raise DatabaseError("Failed to delete goal", original_error=e)


@router.get("/goals/suggestions")
async def get_goal_suggestions(
    user_id: str = Depends(get_current_user_id)
):
    """Get suggested goals based on user's wellness data"""
    try:
        suggestions = await goal_management_service.get_goal_suggestions(user_id)
        return {"suggestions": suggestions}
        
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        raise DatabaseError("Failed to get suggestions", original_error=e)


