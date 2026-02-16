"""
Notifications API Router
Handles push notifications, device tokens, preferences, and notification history.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timezone

from backend.services.notification_service import (
    notification_service,
    WaitingMessage,
    NotificationPayload,
    NotificationType,
)
from backend.database.supabase_client import get_supabase_client
from backend.utils.exceptions import DatabaseError, NotFoundError
from backend.middleware.auth_helper import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class QueueMessageRequest(BaseModel):
    message_text: str
    message_type: str = "coach_message"
    priority: str = "normal"
    scheduled_for: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None


class CheckinRequest(BaseModel):
    message: str
    priority: str = "normal"


class PatternAlertRequest(BaseModel):
    pattern_type: str
    message: str


class AccountabilityNudgeRequest(BaseModel):
    nudge_type: str  # deadline, missed_streak, pattern_broken
    message: str


class RegisterDeviceRequest(BaseModel):
    push_token: str
    platform: str  # 'ios' or 'android'
    expo_push_token: Optional[str] = None  # Expo format token


class UpdatePreferencesRequest(BaseModel):
    notifications_enabled: Optional[bool] = None
    task_reminders_enabled: Optional[bool] = None
    coach_nudges_enabled: Optional[bool] = None
    insights_enabled: Optional[bool] = None
    streak_reminders_enabled: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None  # "HH:MM" format
    quiet_hours_end: Optional[str] = None    # "HH:MM" format
    max_daily_notifications: Optional[int] = None


# =========================================
# Device Token Endpoints
# =========================================

@router.post("/devices/token")
async def register_device_token(
    request: RegisterDeviceRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Register a device for push notifications (new endpoint)"""
    try:
        if request.platform not in ('ios', 'android'):
            return {"success": False, "error": "Invalid platform. Must be 'ios' or 'android'"}

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        # Use expo_push_token if provided, otherwise use push_token
        token = request.expo_push_token or request.push_token

        # Upsert device token (using actual table column names)
        supabase.table('device_tokens').upsert({
            'user_id': user_id,
            'push_token': token,
            'platform': request.platform,
            'active': True,
            'updated_at': now
        }, on_conflict='user_id,platform').execute()

        logger.info(f"Registered device token for user {user_id} on {request.platform}")

        return {"success": True, "message": "Device registered for push notifications"}

    except Exception as e:
        logger.error(f"Error registering device token: {e}")
        raise DatabaseError("Failed to register device", original_error=e)


@router.delete("/devices/token")
async def unregister_device_token(
    token: str = Query(..., description="The device token to unregister"),
    user_id: str = Depends(get_current_user_id)
):
    """Unregister a device token (deactivate, not delete)"""
    try:
        supabase = get_supabase_client()

        result = supabase.table('device_tokens').update({
            'active': False,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('user_id', user_id).eq('push_token', token).execute()

        if not result.data:
            raise NotFoundError("Device token not found")

        return {"success": True, "message": "Device token unregistered"}

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error unregistering device token: {e}")
        raise DatabaseError("Failed to unregister device", original_error=e)


# =========================================
# Notification Preferences Endpoints
# =========================================

@router.get("/preferences")
async def get_notification_preferences(
    user_id: str = Depends(get_current_user_id)
):
    """Get notification preferences for the current user"""
    default_prefs = {
        "notifications_enabled": True,
        "task_reminders_enabled": True,
        "coach_nudges_enabled": True,
        "insights_enabled": True,
        "streak_reminders_enabled": True,
        "quiet_hours_enabled": False,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "max_daily_notifications": 10
    }

    try:
        supabase = get_supabase_client()

        response = supabase.table('notification_preferences').select(
            '*'
        ).eq('user_id', user_id).execute()

        if response.data:
            prefs = response.data[0]
            # Remove internal fields
            prefs.pop('id', None)
            prefs.pop('user_id', None)
            prefs.pop('created_at', None)
            prefs.pop('updated_at', None)
            return {"success": True, "preferences": prefs}

        # Return defaults if no preferences exist
        return {"success": True, "preferences": default_prefs}

    except Exception as e:
        # If table doesn't exist yet, return defaults
        logger.warning(f"Error getting notification preferences (table may not exist): {e}")
        return {"success": True, "preferences": default_prefs}


@router.put("/preferences")
async def update_notification_preferences(
    request: UpdatePreferencesRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Update notification preferences for the current user"""
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        # Build update data from non-None fields
        update_data = {'updated_at': now}

        if request.notifications_enabled is not None:
            update_data['notifications_enabled'] = request.notifications_enabled
        if request.task_reminders_enabled is not None:
            update_data['task_reminders_enabled'] = request.task_reminders_enabled
        if request.coach_nudges_enabled is not None:
            update_data['coach_nudges_enabled'] = request.coach_nudges_enabled
        if request.insights_enabled is not None:
            update_data['insights_enabled'] = request.insights_enabled
        if request.streak_reminders_enabled is not None:
            update_data['streak_reminders_enabled'] = request.streak_reminders_enabled
        if request.quiet_hours_enabled is not None:
            update_data['quiet_hours_enabled'] = request.quiet_hours_enabled
        if request.quiet_hours_start is not None:
            update_data['quiet_hours_start'] = request.quiet_hours_start
        if request.quiet_hours_end is not None:
            update_data['quiet_hours_end'] = request.quiet_hours_end
        if request.max_daily_notifications is not None:
            update_data['max_daily_notifications'] = request.max_daily_notifications

        # Upsert preferences
        supabase.table('notification_preferences').upsert({
            'user_id': user_id,
            **update_data
        }, on_conflict='user_id').execute()

        return {"success": True, "message": "Preferences updated"}

    except Exception as e:
        # If table doesn't exist, log but don't fail
        error_str = str(e).lower()
        if 'does not exist' in error_str or 'relation' in error_str:
            logger.warning(f"notification_preferences table may not exist yet: {e}")
            return {"success": True, "message": "Preferences saved (pending migration)"}
        logger.error(f"Error updating notification preferences: {e}")
        raise DatabaseError("Failed to update preferences", original_error=e)


# =========================================
# Notification History Endpoints
# =========================================

@router.get("/history")
async def get_notification_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id)
):
    """Get notification history for the current user"""
    try:
        history = await notification_service.get_notification_history(
            user_id=user_id,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            "notifications": history,
            "count": len(history)
        }

    except Exception as e:
        logger.error(f"Error getting notification history: {e}")
        raise DatabaseError("Failed to get notification history", original_error=e)


@router.post("/history/{notification_id}/opened")
async def mark_notification_opened(
    notification_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Mark a notification as opened (for analytics)"""
    try:
        supabase = get_supabase_client()

        result = supabase.table('notification_history').update({
            'opened_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', notification_id).eq('user_id', user_id).execute()

        if not result.data:
            raise NotFoundError("Notification not found")

        return {"success": True}

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error marking notification opened: {e}")
        raise DatabaseError("Failed to update notification", original_error=e)


# =========================================
# Task Reminder Endpoints
# =========================================

@router.post("/schedule-task-reminders")
async def schedule_task_reminders(
    user_id: str = Depends(get_current_user_id)
):
    """Schedule reminders for all user's tasks with due dates"""
    try:
        scheduled_count = await notification_service.schedule_task_reminders_for_user(user_id)

        return {
            "success": True,
            "scheduled_count": scheduled_count,
            "message": f"Scheduled {scheduled_count} task reminders"
        }

    except Exception as e:
        logger.error(f"Error scheduling task reminders: {e}")
        raise DatabaseError("Failed to schedule reminders", original_error=e)


# =========================================
# Legacy Endpoint (kept for backwards compatibility)
# =========================================

@router.post("/register-device")
async def register_device(
    request: RegisterDeviceRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Register a device for push notifications (legacy endpoint)"""
    try:
        # Validate platform
        if request.platform not in ('ios', 'android'):
            return {"success": False, "error": "Invalid platform. Must be 'ios' or 'android'"}

        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        # Use expo_push_token if provided, otherwise use push_token
        token = request.expo_push_token or request.push_token

        # Upsert device token (using actual table column names)
        supabase.table('device_tokens').upsert({
            'user_id': user_id,
            'push_token': token,
            'platform': request.platform,
            'active': True,
            'updated_at': now
        }, on_conflict='user_id,platform').execute()

        logger.info(f"Registered device token for user {user_id} on {request.platform}")

        return {"success": True, "message": "Device registered for push notifications"}

    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise DatabaseError("Failed to register device", original_error=e)


@router.post("/queue-message")
async def queue_waiting_message(
    request: QueueMessageRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Queue a message for later delivery"""
    try:
        message = WaitingMessage(
            user_id=user_id,
            message_text=request.message_text,
            message_type=request.message_type,
            priority=request.priority,
            scheduled_for=request.scheduled_for,
            context=request.context
        )

        success = await notification_service.queue_waiting_message(message)

        if success:
            return {"success": True, "message": "Message queued successfully"}
        else:
            raise DatabaseError("Failed to queue message")

    except Exception as e:
        logger.error(f"Error queueing message: {e}")
        raise DatabaseError("Failed to queue message", original_error=e)


@router.get("/waiting-messages")
async def get_waiting_messages(
    user_id: str = Depends(get_current_user_id)
):
    """Get all waiting messages for a user"""
    try:
        messages = await notification_service.get_waiting_messages(user_id)

        return {
            "success": True,
            "messages": messages,
            "count": len(messages)
        }

    except Exception as e:
        logger.error(f"Error getting waiting messages: {e}")
        raise DatabaseError("Failed to get waiting messages", original_error=e)


@router.post("/mark-delivered/{message_id}")
async def mark_message_delivered(
    message_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Mark a waiting message as delivered"""
    try:
        success = await notification_service.mark_message_delivered(message_id)

        if success:
            return {"success": True, "message": "Message marked as delivered"}
        else:
            raise DatabaseError("Failed to mark message as delivered")

    except Exception as e:
        logger.error(f"Error marking message delivered: {e}")
        raise DatabaseError("Failed to mark message as delivered", original_error=e)


@router.post("/coach-checkin")
async def send_coach_checkin(
    request: CheckinRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Send a coach check-in message"""
    try:
        success = await notification_service.send_coach_checkin(
            user_id=user_id,
            message=request.message,
            priority=request.priority
        )

        if success:
            return {"success": True, "message": "Check-in message sent"}
        else:
            raise DatabaseError("Failed to send check-in message")

    except Exception as e:
        logger.error(f"Error sending coach checkin: {e}")
        raise DatabaseError("Failed to send check-in message", original_error=e)


@router.post("/pattern-alert")
async def send_pattern_alert(
    request: PatternAlertRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Send a pattern-based alert message"""
    try:
        success = await notification_service.send_pattern_alert(
            user_id=user_id,
            pattern_type=request.pattern_type,
            message=request.message
        )

        if success:
            return {"success": True, "message": "Pattern alert sent"}
        else:
            raise DatabaseError("Failed to send pattern alert")

    except Exception as e:
        logger.error(f"Error sending pattern alert: {e}")
        raise DatabaseError("Failed to send pattern alert", original_error=e)


@router.post("/accountability-nudge")
async def send_accountability_nudge(
    request: AccountabilityNudgeRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Send an accountability nudge"""
    try:
        success = await notification_service.send_accountability_nudge(
            user_id=user_id,
            nudge_type=request.nudge_type,
            message=request.message
        )

        if success:
            return {"success": True, "message": "Accountability nudge sent"}
        else:
            raise DatabaseError("Failed to send accountability nudge")

    except Exception as e:
        logger.error(f"Error sending accountability nudge: {e}")
        raise DatabaseError("Failed to send accountability nudge", original_error=e)


@router.get("/stats")
async def get_notification_stats(
    user_id: str = Depends(get_current_user_id)
):
    """Get notification statistics for a user"""
    try:
        stats = await notification_service.get_notification_stats(user_id)

        return {
            "success": True,
            "stats": stats
        }

    except Exception as e:
        logger.error(f"Error getting notification stats: {e}")
        raise DatabaseError("Failed to get notification stats", original_error=e)


@router.post("/test-coach-message")
async def test_coach_message(
    user_id: str = "c18f7b13-6d6a-42d6-ac2e-c67cf90e1d1e"  # Test user ID
):
    """Test endpoint to send a coach message"""
    try:
        # Send a test coach message
        success = await notification_service.send_coach_checkin(
            user_id=user_id,
            message="Hey. Still on track today?",
            priority="normal"
        )

        if success:
            return {"success": True, "message": "Test coach message sent"}
        else:
            raise DatabaseError("Failed to send test message")

    except Exception as e:
        logger.error(f"Error sending test coach message: {e}")
        raise DatabaseError("Failed to send test message", original_error=e)


@router.post("/test-all-personalized")
async def test_all_personalized_notifications(
    user_id: str = Depends(get_current_user_id)
):
    """
    Test endpoint to send all notification types with REAL personalized data.
    Uses actual tasks, streaks, and insights from the user's account.
    """
    try:
        supabase = get_supabase_client()
        results = {
            "task_reminder": False,
            "overdue_nudge": False,
            "streak_alert": False,
            "insight": False,
            "coach_message": False,
        }

        # Get user's profile for personalization
        profile_resp = supabase.table("users").select("username").eq("id", user_id).execute()
        username = profile_resp.data[0].get("username", "there") if profile_resp.data else "there"

        # 1. Task Reminder - Get user's next upcoming task
        tasks_resp = supabase.table("shared_todos").select(
            "id, title, due_date, due_time"
        ).eq("user_id", user_id).in_(
            "status", ["pending", "in_progress"]
        ).order("due_date", asc=True).limit(1).execute()

        if tasks_resp.data:
            task = tasks_resp.data[0]
            results["task_reminder"] = await notification_service.send_task_reminder(
                user_id=user_id,
                task_id=task["id"],
                task_title=task["title"],
                minutes_until_due=30
            )

        # 2. Overdue Nudge - Get overdue tasks
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        overdue_resp = supabase.table("shared_todos").select(
            "id, title, due_date"
        ).eq("user_id", user_id).lt("due_date", today).in_(
            "status", ["pending", "in_progress"]
        ).limit(3).execute()

        if overdue_resp.data:
            results["overdue_nudge"] = await notification_service.send_task_overdue_nudge(
                user_id=user_id,
                overdue_tasks=overdue_resp.data
            )
        else:
            # Send a generic nudge if no overdue tasks
            await notification_service.send_notification(
                notification_service.NotificationPayload(
                    user_id=user_id,
                    type=notification_service.NotificationType.COACH_NUDGE,
                    title="Cora",
                    body=f"Hey {username}! How's your day going? Any tasks you want to tackle?",
                    data={"screen": "Tasks"}
                )
            )
            results["overdue_nudge"] = True

        # 3. Streak Alert - Get user's current streak
        streak_resp = supabase.table("user_streaks").select(
            "current_streak"
        ).eq("user_id", user_id).execute()

        current_streak = streak_resp.data[0].get("current_streak", 0) if streak_resp.data else 0
        if current_streak > 0:
            results["streak_alert"] = await notification_service.send_streak_alert(
                user_id=user_id,
                current_streak=current_streak
            )
        else:
            # Encourage starting a streak
            await notification_service.send_notification(
                notification_service.NotificationPayload(
                    user_id=user_id,
                    type=notification_service.NotificationType.STREAK_ALERT,
                    title="Start Your Streak!",
                    body=f"Hey {username}, check in today to start building your streak!",
                    data={"screen": "Home"}
                )
            )
            results["streak_alert"] = True

        # 4. Insight Notification - Get latest insight
        insight_resp = supabase.table("insights").select(
            "id, title"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()

        if insight_resp.data:
            insight = insight_resp.data[0]
            results["insight"] = await notification_service.send_insight_notification(
                user_id=user_id,
                insight_id=insight["id"],
                insight_title=insight["title"]
            )
        else:
            # Send a generic insight teaser
            await notification_service.send_notification(
                notification_service.NotificationPayload(
                    user_id=user_id,
                    type=notification_service.NotificationType.INSIGHT,
                    title="New Insight",
                    body="Keep tracking your tasks and we'll discover patterns in your productivity!",
                    data={"screen": "Insights"}
                )
            )
            results["insight"] = True

        # 5. Coach Message - Personalized check-in
        results["coach_message"] = await notification_service.send_coach_checkin(
            user_id=user_id,
            message=f"Hey {username}! Just checking in. How are you feeling about today's goals?",
            priority="normal"
        )

        return {
            "success": True,
            "results": results,
            "message": "Sent personalized notifications using your real data"
        }

    except Exception as e:
        logger.error(f"Error sending personalized test notifications: {e}")
        raise DatabaseError("Failed to send personalized notifications", original_error=e)


@router.post("/trigger-scheduled-jobs")
async def trigger_scheduled_jobs(
    user_id: str = Depends(get_current_user_id)
):
    """
    Manually trigger all scheduled notification jobs for testing.
    This runs the same jobs that the scheduler runs automatically.
    """
    try:
        results = {
            "task_reminders_scheduled": 0,
            "notifications_processed": 0,
            "overdue_nudges_sent": 0,
            "streak_alerts_sent": 0,
        }

        # 1. Schedule task reminders for this user
        results["task_reminders_scheduled"] = await notification_service.schedule_task_reminders_for_user(user_id)

        # 2. Process any pending scheduled notifications
        results["notifications_processed"] = await notification_service.process_scheduled_notifications()

        # 3. Check and send overdue task nudges
        results["overdue_nudges_sent"] = await notification_service.check_and_send_overdue_task_nudges()

        # 4. Check and send streak alerts
        results["streak_alerts_sent"] = await notification_service.check_and_send_streak_alerts()

        return {
            "success": True,
            "results": results,
            "message": "Triggered all scheduled jobs"
        }

    except Exception as e:
        logger.error(f"Error triggering scheduled jobs: {e}")
        raise DatabaseError("Failed to trigger scheduled jobs", original_error=e)
