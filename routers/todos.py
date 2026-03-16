"""
Shared To-Do List API Endpoints
Handles coach-shared to-do items between user and AI coach.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re
import logging

from backend.database.supabase_client import get_supabase_client
from backend.middleware.auth_helper import get_current_user_id
from backend.utils.exceptions import DatabaseError, NotFoundError, ValidationError
from backend.services.notification_service import notification_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["todos"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


class CreateTodoRequest(BaseModel):
    """Request to create a user-created todo."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    due_time: Optional[str] = None  # Time string (HH:MM)
    reminder_enabled: Optional[bool] = False
    reminder_minutes_before: Optional[int] = Field(30, ge=0, le=10080)
    is_recurring: Optional[bool] = False
    frequency: Optional[str] = "daily"
    icon: Optional[str] = None
    weekly_target: Optional[int] = Field(None, ge=1, le=7)

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f'Priority must be one of: {VALID_PRIORITIES}')
        return v

    @field_validator('due_date')
    @classmethod
    def validate_due_date(cls, v):
        if v is not None and not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError('due_date must be in YYYY-MM-DD format')
        return v

    @field_validator('due_time')
    @classmethod
    def validate_due_time(cls, v):
        if v is not None and not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', v):
            raise ValueError('due_time must be in HH:MM format')
        return v


class CreateCoachTodoRequest(CreateTodoRequest):
    """Request to create a coach-created todo."""
    coach_reasoning: Optional[str] = None
    linked_insight_id: Optional[str] = None


class UpdateTodoStatusRequest(BaseModel):
    """Request to update todo status."""
    status: str

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_STATUSES:
            raise ValueError(f'Status must be one of: {VALID_STATUSES}')
        return v


class UpdateTodoRequest(BaseModel):
    """Request to update todo details."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    priority: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    reminder_enabled: Optional[bool] = None
    reminder_minutes_before: Optional[int] = Field(None, ge=0, le=10080)

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f'Priority must be one of: {VALID_PRIORITIES}')
        return v

    @field_validator('due_date')
    @classmethod
    def validate_due_date(cls, v):
        if v is not None and not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError('due_date must be in YYYY-MM-DD format')
        return v

    @field_validator('due_time')
    @classmethod
    def validate_due_time(cls, v):
        if v is not None and not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', v):
            raise ValueError('due_time must be in HH:MM format')
        return v


# ============================================
# TODO ENDPOINTS
# ============================================

@router.get("/todos")
async def get_todos(user_id: str = Depends(get_current_user_id)):
    """
    Get all active todos for the authenticated user.
    Returns todos where status != 'cancelled', ordered by priority then due_date.
    """
    try:
        supabase = get_supabase_client()

        # Priority order: urgent > high > medium > low
        # We'll sort in Python since Supabase doesn't support custom ordering easily
        response = (
            supabase.table('shared_todos')
            .select('*')
            .eq('user_id', user_id)
            .neq('status', 'cancelled')
            .execute()
        )

        todos = response.data or []

        # Custom priority ordering
        priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}

        # Sort by priority first, then by due_date (nulls last)
        sorted_todos = sorted(
            todos,
            key=lambda t: (
                priority_order.get(t.get('priority', 'medium'), 2),
                t.get('due_date') or '9999-12-31'  # Nulls last
            )
        )

        return sorted_todos

    except Exception as e:
        logger.error(f"Error fetching todos: {e}")
        raise DatabaseError("Failed to fetch todos", original_error=e)


@router.post("/todos")
async def create_todo(request: CreateTodoRequest, user_id: str = Depends(get_current_user_id)):
    """
    Create a new user-created todo.
    """
    try:
        # Validate priority
        valid_priorities = ['low', 'medium', 'high', 'urgent']
        if request.priority and request.priority not in valid_priorities:
            raise ValidationError(f"Invalid priority. Must be one of: {valid_priorities}")

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        todo_data = {
            'user_id': user_id,
            'title': request.title,
            'description': request.description,
            'created_by': 'user',
            'status': 'pending',
            'priority': request.priority or 'medium',
            'due_date': request.due_date,
            'due_time': request.due_time,
            'reminder_enabled': request.reminder_enabled or False,
            'reminder_minutes_before': request.reminder_minutes_before or 30,
            'is_recurring': request.is_recurring or False,
            'frequency': request.frequency or 'daily',
            'icon': request.icon,
            'created_at': now,
            'updated_at': now
        }

        response = supabase.table('shared_todos').insert(todo_data).execute()

        if response.data and len(response.data) > 0:
            created_todo = response.data[0]

            # Schedule reminder if enabled and has due date
            if request.reminder_enabled and request.due_date:
                try:
                    await notification_service.schedule_task_reminders_for_user(user_id)
                    logger.info(f"Scheduled reminder for new task: {created_todo['id']}")
                except Exception as reminder_error:
                    logger.warning(f"Failed to schedule reminder for task: {reminder_error}")

            return created_todo

        raise DatabaseError("Failed to create todo")

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error creating todo: {e}")
        raise DatabaseError("Failed to create todo", original_error=e)


@router.post("/todos/coach")
async def create_coach_todo(request: CreateCoachTodoRequest, user_id: str = Depends(get_current_user_id)):
    """
    Create a new coach-created todo.
    This endpoint is typically called by the AI coach to suggest tasks.
    """
    try:
        # Validate priority
        valid_priorities = ['low', 'medium', 'high', 'urgent']
        if request.priority and request.priority not in valid_priorities:
            raise ValidationError(f"Invalid priority. Must be one of: {valid_priorities}")

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        todo_data = {
            'user_id': user_id,
            'title': request.title,
            'description': request.description,
            'created_by': 'coach',
            'status': 'pending',
            'priority': request.priority or 'medium',
            'due_date': request.due_date,
            'due_time': request.due_time,
            'reminder_enabled': request.reminder_enabled or False,
            'reminder_minutes_before': request.reminder_minutes_before or 30,
            'coach_reasoning': request.coach_reasoning,
            'linked_insight_id': request.linked_insight_id,
            'created_at': now,
            'updated_at': now
        }

        response = supabase.table('shared_todos').insert(todo_data).execute()

        if response.data and len(response.data) > 0:
            created_todo = response.data[0]

            # Send push notification to user about the new coach task
            try:
                await notification_service.send_coach_task_notification(
                    user_id=user_id,
                    task_id=created_todo['id'],
                    task_title=created_todo['title'],
                    coach_reasoning=created_todo.get('coach_reasoning')
                )
            except Exception as notif_error:
                # Don't fail the request if notification fails
                logger.warning(f"Failed to send coach task notification: {notif_error}")

            # Schedule reminder if enabled and has due date
            if request.reminder_enabled and request.due_date:
                try:
                    await notification_service.schedule_task_reminders_for_user(user_id)
                    logger.info(f"Scheduled reminder for coach task: {created_todo['id']}")
                except Exception as reminder_error:
                    logger.warning(f"Failed to schedule reminder for coach task: {reminder_error}")

            return created_todo

        raise DatabaseError("Failed to create coach todo")

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error creating coach todo: {e}")
        raise DatabaseError("Failed to create coach todo", original_error=e)


@router.put("/todos/{todo_id}/status")
async def update_todo_status(
    todo_id: str,
    request: UpdateTodoStatusRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update the status of a todo.
    If status is 'completed', sets completed_at timestamp.
    """
    try:
        # Validate status
        valid_statuses = ['pending', 'in_progress', 'completed', 'cancelled']
        if request.status not in valid_statuses:
            raise ValidationError(f"Invalid status. Must be one of: {valid_statuses}")

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        update_data = {
            'status': request.status,
            'updated_at': now
        }

        # Set completed_at if marking as completed
        if request.status == 'completed':
            update_data['completed_at'] = now

        response = (
            supabase.table('shared_todos')
            .update(update_data)
            .eq('id', todo_id)
            .eq('user_id', user_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return response.data[0]

        raise NotFoundError("Todo not found")

    except (ValidationError, NotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error updating todo status: {e}")
        raise DatabaseError("Failed to update todo status", original_error=e)


@router.put("/todos/{todo_id}")
async def update_todo(
    todo_id: str,
    request: UpdateTodoRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update todo details (title, description, priority, due_date, etc.).
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        # Build update data from non-None fields
        update_data = {'updated_at': now}

        if request.title is not None:
            update_data['title'] = request.title
        if request.description is not None:
            update_data['description'] = request.description
        if request.priority is not None:
            valid_priorities = ['low', 'medium', 'high', 'urgent']
            if request.priority not in valid_priorities:
                raise ValidationError(f"Invalid priority. Must be one of: {valid_priorities}")
            update_data['priority'] = request.priority
        if request.due_date is not None:
            update_data['due_date'] = request.due_date
        if request.due_time is not None:
            update_data['due_time'] = request.due_time
        if request.reminder_enabled is not None:
            update_data['reminder_enabled'] = request.reminder_enabled
        if request.reminder_minutes_before is not None:
            update_data['reminder_minutes_before'] = request.reminder_minutes_before

        response = (
            supabase.table('shared_todos')
            .update(update_data)
            .eq('id', todo_id)
            .eq('user_id', user_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            updated_todo = response.data[0]

            # Re-schedule reminders if reminder settings changed
            if request.reminder_enabled is not None or request.due_date is not None or request.due_time is not None:
                try:
                    await notification_service.schedule_task_reminders_for_user(user_id)
                    logger.info(f"Re-scheduled reminders for user after task update: {todo_id}")
                except Exception as reminder_error:
                    logger.warning(f"Failed to re-schedule reminders: {reminder_error}")

            return updated_todo

        raise NotFoundError("Todo not found")

    except (ValidationError, NotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error updating todo: {e}")
        raise DatabaseError("Failed to update todo", original_error=e)


@router.delete("/todos/{todo_id}")
async def delete_todo(todo_id: str, user_id: str = Depends(get_current_user_id)):
    """
    Soft delete a todo by setting status to 'cancelled'.
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        response = (
            supabase.table('shared_todos')
            .update({
                'status': 'cancelled',
                'updated_at': now
            })
            .eq('id', todo_id)
            .eq('user_id', user_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return {"success": True, "message": "Todo cancelled"}

        raise NotFoundError("Todo not found")

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting todo: {e}")
        raise DatabaseError("Failed to delete todo", original_error=e)


# ============================================
# RECURRING TASK ENDPOINTS
# ============================================

def _recalculate_streak(supabase, task_id: str) -> tuple[int, int]:
    """
    Walk back from today counting consecutive completed days.
    Returns (current_streak, longest_streak).
    """
    response = (
        supabase.table("task_completions")
        .select("date")
        .eq("task_id", task_id)
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

    # Get existing longest streak from the task record
    task_resp = (
        supabase.table("shared_todos")
        .select("longest_streak")
        .eq("id", task_id)
        .limit(1)
        .execute()
    )
    existing_longest = 0
    if task_resp.data:
        existing_longest = task_resp.data[0].get("longest_streak", 0) or 0

    longest = max(streak, existing_longest)
    return streak, longest


@router.get("/todos/today")
async def get_recurring_todos_today(user_id: str = Depends(get_current_user_id)):
    """Get all recurring tasks with today's completion status and weekly progress."""
    try:
        supabase = get_supabase_client()
        today = date.today()
        today_str = today.isoformat()

        # Get active recurring tasks, ordered by created_at
        # (sort_order column may not exist yet; safe fallback)
        todos_resp = (
            supabase.table("shared_todos")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_recurring", True)
            .neq("status", "cancelled")
            .order("created_at")
            .execute()
        )
        todos = todos_resp.data or []

        if not todos:
            return []

        todo_ids = [t["id"] for t in todos]

        # Get today's completions
        completions_resp = (
            supabase.table("task_completions")
            .select("task_id")
            .eq("user_id", user_id)
            .eq("date", today_str)
            .in_("task_id", todo_ids)
            .execute()
        )
        completed_ids = {c["task_id"] for c in (completions_resp.data or [])}

        # For weekly tasks, get this week's completion count
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        weekly_completions_resp = (
            supabase.table("task_completions")
            .select("task_id")
            .eq("user_id", user_id)
            .gte("date", week_start)
            .lte("date", today_str)
            .in_("task_id", todo_ids)
            .execute()
        )
        weekly_counts: dict[str, int] = {}
        for c in (weekly_completions_resp.data or []):
            tid = c["task_id"]
            weekly_counts[tid] = weekly_counts.get(tid, 0) + 1

        for todo in todos:
            todo["completed_today"] = todo["id"] in completed_ids
            if todo.get("frequency") == "weekly":
                todo["weekly_completed"] = weekly_counts.get(todo["id"], 0)
                todo["weekly_target"] = todo.get("weekly_target") or 7

        return todos

    except Exception as e:
        logger.error(f"Error fetching recurring todos today: {e}")
        raise DatabaseError("Failed to fetch recurring todos", original_error=e)


@router.post("/todos/{todo_id}/toggle")
async def toggle_recurring_todo(
    todo_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Toggle today's completion for a recurring task. Recalculates streak."""
    try:
        supabase = get_supabase_client()
        today_str = date.today().isoformat()
        now = datetime.now(timezone.utc).isoformat()

        # Check if already completed today
        existing = (
            supabase.table("task_completions")
            .select("id")
            .eq("task_id", todo_id)
            .eq("date", today_str)
            .limit(1)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            # Un-complete: delete the completion
            supabase.table("task_completions").delete().eq(
                "id", existing.data[0]["id"]
            ).execute()
            completed_today = False
        else:
            # Complete: insert completion
            supabase.table("task_completions").insert(
                {
                    "task_id": todo_id,
                    "user_id": user_id,
                    "date": today_str,
                    "completed_at": now,
                }
            ).execute()
            completed_today = True

        # Recalculate streak
        streak, longest = _recalculate_streak(supabase, todo_id)

        # Update task record
        update_data = {
            "streak_count": streak,
            "longest_streak": longest,
            "updated_at": now,
        }

        todo_resp = (
            supabase.table("shared_todos")
            .update(update_data)
            .eq("id", todo_id)
            .eq("user_id", user_id)
            .execute()
        )

        if todo_resp.data and len(todo_resp.data) > 0:
            todo = todo_resp.data[0]
            todo["completed_today"] = completed_today

            # Detect streak milestones for celebration
            milestones = [3, 7, 14, 21, 30, 50, 100, 365]
            todo["streak_milestone"] = streak if (completed_today and streak in milestones) else None

            return todo

        raise NotFoundError("Task not found")

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error toggling recurring todo: {e}")
        raise DatabaseError("Failed to toggle recurring todo", original_error=e)


@router.get("/todos/completions")
async def get_completion_history(
    user_id: str = Depends(get_current_user_id),
    days: int = 30,
):
    """Get completion history for the heatmap/contribution grid."""
    try:
        supabase = get_supabase_client()
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        response = (
            supabase.table("task_completions")
            .select("date, task_id")
            .eq("user_id", user_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
        )
        rows = response.data or []

        # Group by date
        day_counts: dict[str, int] = {}
        for r in rows:
            d = r["date"]
            day_counts[d] = day_counts.get(d, 0) + 1

        # Build complete date range with zeros for missing days
        result = []
        current = start_date
        while current <= end_date:
            d_str = current.isoformat()
            result.append({"date": d_str, "count": day_counts.get(d_str, 0)})
            current += timedelta(days=1)

        return result

    except Exception as e:
        logger.error(f"Error fetching completion history: {e}")
        raise DatabaseError("Failed to fetch completion history", original_error=e)


class ReorderRequest(BaseModel):
    """Request to reorder recurring tasks."""
    task_ids: list[str]  # Ordered list of task IDs


@router.put("/todos/reorder")
async def reorder_recurring_todos(
    request: ReorderRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Reorder recurring tasks. Updates sort_order if column exists, otherwise no-op."""
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        for index, task_id in enumerate(request.task_ids):
            try:
                supabase.table("shared_todos").update({
                    "sort_order": index,
                    "updated_at": now,
                }).eq("id", task_id).eq("user_id", user_id).execute()
            except Exception:
                # sort_order column may not exist yet; just update timestamp
                supabase.table("shared_todos").update({
                    "updated_at": now,
                }).eq("id", task_id).eq("user_id", user_id).execute()
                break

        return {"success": True}

    except Exception as e:
        logger.error(f"Error reordering todos: {e}")
        raise DatabaseError("Failed to reorder todos", original_error=e)
