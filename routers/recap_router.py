"""
Weekly Recap API Endpoint
Aggregates mood, energy, sleep, steps, recurring tasks, and streak data for a given period.
"""

from fastapi import APIRouter, Depends, Query
from datetime import date, timedelta
import asyncio
import logging

from backend.database.supabase_client import get_supabase_client
from backend.middleware.auth_helper import get_current_user_id
from backend.utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recap"])


def _safe_avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0


@router.get("/recap/weekly")
async def get_weekly_recap(
    user_id: str = Depends(get_current_user_id),
    days: int = Query(default=7, ge=1, le=90),
):
    """
    Get aggregated recap data for the last N days.
    Returns trends for mood, energy, sleep, steps, recurring tasks, and streak info.
    """
    try:
        supabase = get_supabase_client()
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        # Run all queries concurrently
        mood_energy_task = asyncio.to_thread(
            _fetch_mood_energy, supabase, user_id, start_str, end_str
        )
        health_task = asyncio.to_thread(
            _fetch_health_trends, supabase, user_id, start_str, end_str
        )
        tasks_task = asyncio.to_thread(
            _fetch_task_completions, supabase, user_id, start_str, end_str
        )
        streak_task = asyncio.to_thread(
            _fetch_streak_info, supabase, user_id
        )

        mood_energy, health, tasks_data, streak = await asyncio.gather(
            mood_energy_task, health_task, tasks_task, streak_task
        )

        mood_trend = mood_energy.get("mood", [])
        energy_trend = mood_energy.get("energy", [])
        sleep_trend = health.get("sleep", [])
        steps_trend = health.get("steps", [])
        tasks_by_day = tasks_data.get("by_day", [])
        tasks_total = tasks_data.get("total", 0)

        # Build coach summary string
        parts = []
        mood_vals = [m["value"] for m in mood_trend if m.get("value")]
        if mood_vals:
            avg = _safe_avg(mood_vals)
            parts.append(f"Avg mood: {avg}/10")
        energy_vals = [e["value"] for e in energy_trend if e.get("value")]
        if energy_vals:
            avg = _safe_avg(energy_vals)
            parts.append(f"Avg energy: {avg}/10")
        if tasks_total > 0:
            parts.append(f"{tasks_total} tasks completed")
        if streak.get("current_streak", 0) > 0:
            parts.append(f"{streak['current_streak']}-day streak")

        coach_summary = ". ".join(parts) + "." if parts else "No data recorded this week."

        return {
            "period_start": start_str,
            "period_end": end_str,
            "mood_trend": mood_trend,
            "energy_trend": energy_trend,
            "sleep_trend": sleep_trend,
            "steps_trend": steps_trend,
            "tasks_completed_by_day": tasks_by_day,
            "tasks_completed_total": tasks_total,
            "tasks_streak": streak.get("current_streak", 0),
            "coach_summary": coach_summary,
        }

    except Exception as e:
        logger.error(f"Error fetching weekly recap: {e}")
        raise DatabaseError("Failed to fetch weekly recap", original_error=e)


# ============================================
# PRIVATE QUERY HELPERS (run in threadpool)
# ============================================

def _fetch_mood_energy(supabase, user_id: str, start: str, end: str) -> dict:
    """Fetch mood and energy from user_metrics."""
    try:
        response = (
            supabase.table("user_metrics")
            .select("metric_type, value, logged_at")
            .eq("user_id", user_id)
            .in_("metric_type", ["mood", "energy"])
            .gte("logged_at", start)
            .lte("logged_at", end)
            .order("logged_at")
            .execute()
        )
        rows = response.data or []
        mood = [{"date": r["logged_at"][:10], "value": r["value"]} for r in rows if r["metric_type"] == "mood"]
        energy = [{"date": r["logged_at"][:10], "value": r["value"]} for r in rows if r["metric_type"] == "energy"]
        return {"mood": mood, "energy": energy}
    except Exception as e:
        logger.error(f"Error fetching mood/energy: {e}")
        return {"mood": [], "energy": []}


def _fetch_health_trends(supabase, user_id: str, start: str, end: str) -> dict:
    """Fetch sleep and steps from health_metrics."""
    try:
        response = (
            supabase.table("health_metrics")
            .select("metric_type, value, recorded_at")
            .eq("user_id", user_id)
            .in_("metric_type", ["sleep_hours", "steps"])
            .gte("recorded_at", start)
            .lte("recorded_at", end + "T23:59:59")
            .order("recorded_at")
            .execute()
        )
        rows = response.data or []
        sleep = [{"date": r["recorded_at"][:10], "value": r["value"]} for r in rows if r["metric_type"] == "sleep_hours"]
        steps = [{"date": r["recorded_at"][:10], "value": r["value"]} for r in rows if r["metric_type"] == "steps"]
        return {"sleep": sleep, "steps": steps}
    except Exception as e:
        logger.error(f"Error fetching health trends: {e}")
        return {"sleep": [], "steps": []}


def _fetch_task_completions(supabase, user_id: str, start: str, end: str) -> dict:
    """Fetch task completions (recurring tasks) grouped by day."""
    try:
        response = (
            supabase.table("task_completions")
            .select("date")
            .eq("user_id", user_id)
            .gte("date", start)
            .lte("date", end)
            .execute()
        )
        rows = response.data or []

        # Group by day
        day_counts: dict[str, int] = {}
        for r in rows:
            d = r["date"]
            day_counts[d] = day_counts.get(d, 0) + 1

        by_day = [{"date": k, "count": v} for k, v in sorted(day_counts.items())]
        total = sum(day_counts.values())

        return {"by_day": by_day, "total": total}
    except Exception as e:
        logger.error(f"Error fetching task completions: {e}")
        return {"by_day": [], "total": 0}


def _fetch_streak_info(supabase, user_id: str) -> dict:
    """Fetch streak info from user_streaks."""
    try:
        response = (
            supabase.table("user_streaks")
            .select("current_streak, longest_streak")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]
        return {"current_streak": 0, "longest_streak": 0}
    except Exception as e:
        logger.error(f"Error fetching streak info: {e}")
        return {"current_streak": 0, "longest_streak": 0}
