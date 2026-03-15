"""
Habits API Endpoints
Handles habit CRUD and daily toggle/streak tracking.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

from backend.database.supabase_client import get_supabase_client
from backend.middleware.auth_helper import get_current_user_id
from backend.utils.exceptions import DatabaseError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["habits"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class CreateHabitRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    icon: Optional[str] = "checkmark-circle-outline"
    frequency: Optional[str] = "daily"


class UpdateHabitRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    icon: Optional[str] = None


# ============================================
# HELPER: Streak calculation
# ============================================

def _recalculate_streak(supabase, habit_id: str) -> tuple[int, int]:
    """
    Walk back from today counting consecutive completed days.
    Returns (current_streak, longest_streak).
    """
    response = (
        supabase.table("habit_completions")
        .select("date")
        .eq("habit_id", habit_id)
        .order("date", desc=True)
        .limit(365)
        .execute()
    )

    if not response.data:
        return 0, 0

    completed_dates = {row["date"] for row in response.data}
    today = date.today()

    # Count current streak
    streak = 0
    check_date = today
    while check_date.isoformat() in completed_dates:
        streak += 1
        check_date -= timedelta(days=1)

    # If today isn't completed but yesterday is, check from yesterday
    if streak == 0:
        check_date = today - timedelta(days=1)
        while check_date.isoformat() in completed_dates:
            streak += 1
            check_date -= timedelta(days=1)

    # Get existing longest streak from the habit record
    habit_resp = (
        supabase.table("habits")
        .select("longest_streak")
        .eq("id", habit_id)
        .limit(1)
        .execute()
    )
    existing_longest = 0
    if habit_resp.data:
        existing_longest = habit_resp.data[0].get("longest_streak", 0)

    longest = max(streak, existing_longest)
    return streak, longest


# ============================================
# ENDPOINTS
# ============================================

@router.get("/habits/today")
async def get_habits_today(user_id: str = Depends(get_current_user_id)):
    """Get all active habits with today's completion status."""
    try:
        supabase = get_supabase_client()
        today_str = date.today().isoformat()

        # Get active habits
        habits_resp = (
            supabase.table("habits")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at")
            .execute()
        )
        habits = habits_resp.data or []

        if not habits:
            return []

        habit_ids = [h["id"] for h in habits]

        # Get today's completions
        completions_resp = (
            supabase.table("habit_completions")
            .select("habit_id")
            .eq("user_id", user_id)
            .eq("date", today_str)
            .in_("habit_id", habit_ids)
            .execute()
        )
        completed_ids = {c["habit_id"] for c in (completions_resp.data or [])}

        # Add completed_today flag
        for habit in habits:
            habit["completed_today"] = habit["id"] in completed_ids

        return habits

    except Exception as e:
        logger.error(f"Error fetching habits today: {e}")
        raise DatabaseError("Failed to fetch habits", original_error=e)


@router.get("/habits")
async def get_habits(user_id: str = Depends(get_current_user_id)):
    """Get all active habits."""
    try:
        supabase = get_supabase_client()
        response = (
            supabase.table("habits")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at")
            .execute()
        )
        return response.data or []

    except Exception as e:
        logger.error(f"Error fetching habits: {e}")
        raise DatabaseError("Failed to fetch habits", original_error=e)


@router.post("/habits")
async def create_habit(
    request: CreateHabitRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new habit."""
    try:
        if request.frequency and request.frequency not in ("daily", "weekly"):
            raise ValidationError("Frequency must be 'daily' or 'weekly'")

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        habit_data = {
            "user_id": user_id,
            "title": request.title,
            "icon": request.icon or "checkmark-circle-outline",
            "frequency": request.frequency or "daily",
            "streak_count": 0,
            "longest_streak": 0,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        response = supabase.table("habits").insert(habit_data).execute()

        if response.data and len(response.data) > 0:
            habit = response.data[0]
            habit["completed_today"] = False
            return habit

        raise DatabaseError("Failed to create habit")

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error creating habit: {e}")
        raise DatabaseError("Failed to create habit", original_error=e)


@router.put("/habits/{habit_id}")
async def update_habit(
    habit_id: str,
    request: UpdateHabitRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update habit title/icon."""
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        update_data = {"updated_at": now}
        if request.title is not None:
            update_data["title"] = request.title
        if request.icon is not None:
            update_data["icon"] = request.icon

        response = (
            supabase.table("habits")
            .update(update_data)
            .eq("id", habit_id)
            .eq("user_id", user_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return response.data[0]

        raise NotFoundError("Habit not found")

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error updating habit: {e}")
        raise DatabaseError("Failed to update habit", original_error=e)


@router.delete("/habits/{habit_id}")
async def delete_habit(
    habit_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Soft delete a habit (set is_active=false)."""
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        response = (
            supabase.table("habits")
            .update({"is_active": False, "updated_at": now})
            .eq("id", habit_id)
            .eq("user_id", user_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return {"success": True, "message": "Habit deleted"}

        raise NotFoundError("Habit not found")

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting habit: {e}")
        raise DatabaseError("Failed to delete habit", original_error=e)


@router.post("/habits/{habit_id}/toggle")
async def toggle_habit(
    habit_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Toggle today's completion for a habit. Recalculates streak."""
    try:
        supabase = get_supabase_client()
        today_str = date.today().isoformat()
        now = datetime.now(timezone.utc).isoformat()

        # Check if already completed today
        existing = (
            supabase.table("habit_completions")
            .select("id")
            .eq("habit_id", habit_id)
            .eq("date", today_str)
            .limit(1)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            # Un-complete: delete the completion
            supabase.table("habit_completions").delete().eq(
                "id", existing.data[0]["id"]
            ).execute()
            completed_today = False
        else:
            # Complete: insert completion
            supabase.table("habit_completions").insert(
                {
                    "habit_id": habit_id,
                    "user_id": user_id,
                    "date": today_str,
                    "completed_at": now,
                }
            ).execute()
            completed_today = True

        # Recalculate streak
        streak, longest = _recalculate_streak(supabase, habit_id)

        # Update habit record
        update_data = {
            "streak_count": streak,
            "longest_streak": longest,
            "updated_at": now,
        }
        if completed_today:
            update_data["last_completed_at"] = now

        habit_resp = (
            supabase.table("habits")
            .update(update_data)
            .eq("id", habit_id)
            .eq("user_id", user_id)
            .execute()
        )

        if habit_resp.data and len(habit_resp.data) > 0:
            habit = habit_resp.data[0]
            habit["completed_today"] = completed_today
            return habit

        raise NotFoundError("Habit not found")

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error toggling habit: {e}")
        raise DatabaseError("Failed to toggle habit", original_error=e)
