"""
Shared To-Do List API Endpoints
Handles coach-shared to-do items between user and AI coach.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
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

class CreateTodoRequest(BaseModel):
    """Request to create a user-created todo."""
    title: str
    description: Optional[str] = None
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    due_time: Optional[str] = None  # Time string (HH:MM)
    reminder_enabled: Optional[bool] = False
    reminder_minutes_before: Optional[int] = 30


class CreateCoachTodoRequest(CreateTodoRequest):
    """Request to create a coach-created todo."""
    coach_reasoning: Optional[str] = None
    linked_insight_id: Optional[str] = None


class UpdateTodoStatusRequest(BaseModel):
    """Request to update todo status."""
    status: str  # 'pending', 'in_progress', 'completed', 'cancelled'


class UpdateTodoRequest(BaseModel):
    """Request to update todo details."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    reminder_enabled: Optional[bool] = None
    reminder_minutes_before: Optional[int] = None


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
