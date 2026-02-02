"""
Notification Service
Handles push notifications for coach messages, task reminders, insights, and nudges.
"""

import logging
import asyncio
import httpx
from datetime import datetime, timedelta, time, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Expo Push Notification API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationType(str, Enum):
    """Types of notifications the system can send"""
    TASK_REMINDER = "task_reminder"
    COACH_NUDGE = "coach_nudge"
    INSIGHT = "insight"
    STREAK_ALERT = "streak_alert"
    COACH_TASK = "coach_task"
    COACH_MESSAGE = "coach_message"
    PATTERN_ALERT = "pattern_alert"
    ACCOUNTABILITY_NUDGE = "accountability_nudge"


@dataclass
class NotificationPayload:
    """Structured notification payload"""
    user_id: str
    type: NotificationType
    title: str
    body: str
    reference_type: Optional[str] = None  # 'todo' | 'insight' | 'streak'
    reference_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None  # Extra data for deep linking
    scheduled_for: Optional[datetime] = None


@dataclass
class WaitingMessage:
    user_id: str
    message_text: str
    message_type: str = "coach_message"
    priority: str = "normal"  # low, normal, high, urgent
    scheduled_for: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None

class NotificationService:
    """Service for managing waiting messages and notifications"""

    def __init__(self):
        self.supabase = get_supabase_client()
        self.message_queue: List[WaitingMessage] = []

    async def queue_waiting_message(self, message: WaitingMessage) -> bool:
        """Queue a message to be sent when user becomes available"""
        try:
            # Store in database for persistence
            await self._store_waiting_message(message)

            # Add to in-memory queue for immediate processing
            self.message_queue.append(message)

            # Attempt immediate delivery if user is active
            if await self._is_user_active(message.user_id):
                await self._deliver_message_immediately(message)
            else:
                logger.info(f"Queued waiting message for user {message.user_id}")

            return True

        except Exception as e:
            logger.error(f"Error queueing waiting message: {e}")
            return False

    async def get_waiting_messages(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all waiting messages for a user"""
        try:
            response = self.supabase.table('waiting_messages').select('*').eq(
                'user_id', user_id
            ).eq('delivered', False).order('created_at', asc=True).execute()

            messages = []
            if response.data:
                for msg in response.data:
                    messages.append({
                        "id": msg['id'],
                        "message_text": msg['message_text'],
                        "message_type": msg.get('message_type', 'coach_message'),
                        "priority": msg.get('priority', 'normal'),
                        "created_at": msg['created_at'],
                        "context": msg.get('context', {})
                    })

            return messages

        except Exception as e:
            logger.error(f"Error getting waiting messages for {user_id}: {e}")
            return []

    async def mark_message_delivered(self, message_id: str) -> bool:
        """Mark a waiting message as delivered"""
        try:
            self.supabase.table('waiting_messages').update({
                'delivered': True,
                'delivered_at': datetime.now().isoformat()
            }).eq('id', message_id).execute()

            return True

        except Exception as e:
            logger.error(f"Error marking message delivered: {e}")
            return False

    async def process_delayed_messages(self) -> int:
        """Process messages that are scheduled for future delivery"""
        try:
            now = datetime.now()

            # Get messages scheduled for now or past
            response = self.supabase.table('waiting_messages').select('*').eq(
                'delivered', False
            ).lte('scheduled_for', now.isoformat()).execute()

            processed_count = 0
            if response.data:
                for msg in response.data:
                    # Check if user is now active
                    if await self._is_user_active(msg['user_id']):
                        await self._deliver_message_immediately(WaitingMessage(
                            user_id=msg['user_id'],
                            message_text=msg['message_text'],
                            message_type=msg.get('message_type', 'coach_message'),
                            priority=msg.get('priority', 'normal'),
                            context=msg.get('context', {})
                        ))

                        # Mark as delivered
                        await self.mark_message_delivered(msg['id'])
                        processed_count += 1

            return processed_count

        except Exception as e:
            logger.error(f"Error processing delayed messages: {e}")
            return 0

    async def send_coach_checkin(self, user_id: str, message: str, priority: str = "normal") -> bool:
        """Send a coach check-in message"""
        waiting_message = WaitingMessage(
            user_id=user_id,
            message_text=message,
            message_type="coach_checkin",
            priority=priority
        )

        return await self.queue_waiting_message(waiting_message)

    async def send_pattern_alert(self, user_id: str, pattern_type: str, message: str) -> bool:
        """Send a pattern-based alert message"""
        waiting_message = WaitingMessage(
            user_id=user_id,
            message_text=message,
            message_type="pattern_alert",
            priority="high"
        )

        return await self.queue_waiting_message(waiting_message)

    async def send_accountability_nudge(self, user_id: str, nudge_type: str, message: str) -> bool:
        """Send an accountability nudge"""
        waiting_message = WaitingMessage(
            user_id=user_id,
            message_text=message,
            message_type="accountability_nudge",
            priority="urgent" if nudge_type == "deadline" else "normal"
        )

        return await self.queue_waiting_message(waiting_message)

    async def _store_waiting_message(self, message: WaitingMessage) -> bool:
        """Store waiting message in database"""
        try:
            self.supabase.table('waiting_messages').insert({
                'user_id': message.user_id,
                'message_text': message.message_text,
                'message_type': message.message_type,
                'priority': message.priority,
                'scheduled_for': message.scheduled_for.isoformat() if message.scheduled_for else None,
                'context': message.context or {},
                'delivered': False,
                'created_at': datetime.now().isoformat()
            }).execute()

            return True

        except Exception as e:
            logger.error(f"Error storing waiting message: {e}")
            return False

    async def _is_user_active(self, user_id: str) -> bool:
        """Check if user is currently active (has recent app usage)"""
        try:
            # Check for recent coach messages (user replied recently)
            recent_cutoff = (datetime.now() - timedelta(hours=2)).isoformat()

            response = self.supabase.table('messages').select('id').eq(
                'user_id', user_id
            ).gte('created_at', recent_cutoff).execute()

            return len(response.data) > 0 if response.data else False

        except Exception as e:
            logger.error(f"Error checking user activity: {e}")
            return False

    async def _should_send_notification(self, user_id: str) -> bool:
        """
        Check if notifications should be sent based on user preferences.
        Checks:
        - push_notifications enabled
        - Not in quiet hours
        """
        try:
            # Get user preferences
            response = self.supabase.table('user_preferences').select(
                'push_notifications, quiet_hours_enabled, quiet_hours_start, quiet_hours_end'
            ).eq('user_id', user_id).single().execute()

            if not response.data:
                # No preferences found, allow notifications by default
                return True

            prefs = response.data

            # Check if push notifications are enabled
            if prefs.get('push_notifications') is False:
                logger.info(f"Push notifications disabled for user {user_id}")
                return False

            # Check quiet hours
            if prefs.get('quiet_hours_enabled'):
                quiet_start_str = prefs.get('quiet_hours_start')
                quiet_end_str = prefs.get('quiet_hours_end')

                if quiet_start_str and quiet_end_str:
                    try:
                        # Parse quiet hours (expected format: "HH:MM" or "HH:MM:SS")
                        quiet_start = datetime.strptime(quiet_start_str.split(':')[0] + ':' + quiet_start_str.split(':')[1], '%H:%M').time()
                        quiet_end = datetime.strptime(quiet_end_str.split(':')[0] + ':' + quiet_end_str.split(':')[1], '%H:%M').time()

                        now_time = datetime.now().time()

                        # Handle overnight quiet hours (e.g., 22:00 to 07:00)
                        if quiet_start > quiet_end:
                            # Overnight range
                            in_quiet_hours = now_time >= quiet_start or now_time <= quiet_end
                        else:
                            # Same-day range
                            in_quiet_hours = quiet_start <= now_time <= quiet_end

                        if in_quiet_hours:
                            logger.info(f"User {user_id} is in quiet hours ({quiet_start_str} - {quiet_end_str})")
                            return False
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Error parsing quiet hours for user {user_id}: {e}")

            return True

        except Exception as e:
            logger.error(f"Error checking notification preferences for {user_id}: {e}")
            # On error, default to allowing notification
            return True

    async def _send_expo_push(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a push notification via Expo's push notification service.

        Args:
            token: Expo push token (e.g., "ExponentPushToken[xxx]")
            title: Notification title
            body: Notification body text
            data: Optional data payload for the notification

        Returns:
            bool: True if notification was sent successfully
        """
        try:
            message = {
                "to": token,
                "title": title,
                "body": body,
                "sound": "default",
                "priority": "high",
            }

            if data:
                message["data"] = data

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=message,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip, deflate",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    # Check for errors in the response
                    if result.get("data") and len(result["data"]) > 0:
                        ticket = result["data"][0]
                        if ticket.get("status") == "ok":
                            logger.info(f"Push notification sent successfully to token {token[:20]}...")
                            return True
                        else:
                            logger.warning(f"Push notification error: {ticket.get('message', 'Unknown error')}")
                            return False
                    return True
                else:
                    logger.error(f"Expo push API error: {response.status_code} - {response.text}")
                    return False

        except httpx.TimeoutException:
            logger.error(f"Timeout sending push notification to {token[:20]}...")
            return False
        except Exception as e:
            logger.error(f"Error sending Expo push notification: {e}")
            return False

    async def _get_device_tokens(self, user_id: str) -> List[Dict[str, str]]:
        """Get all active device tokens for a user"""
        try:
            response = self.supabase.table('device_tokens').select(
                'push_token, platform'
            ).eq('user_id', user_id).eq('active', True).execute()

            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Error getting device tokens for {user_id}: {e}")
            return []

    async def _deliver_message_immediately(self, message: WaitingMessage) -> bool:
        """Deliver message immediately via push notification"""
        try:
            # Check if we should send notification based on user preferences
            if not await self._should_send_notification(message.user_id):
                logger.info(f"Notification suppressed for user {message.user_id} due to preferences")
                return False

            # Get device tokens for the user
            device_tokens = await self._get_device_tokens(message.user_id)

            if not device_tokens:
                logger.info(f"No device tokens found for user {message.user_id}")
                return False

            # Determine notification title based on message type
            title_map = {
                "coach_message": "CoreSense Coach",
                "coach_checkin": "CoreSense",
                "pattern_alert": "Pattern Detected",
                "accountability_nudge": "Quick Check-in",
            }
            title = title_map.get(message.message_type, "CoreSense")

            # Prepare notification data payload
            data = {
                "type": message.message_type,
                "priority": message.priority,
                "screen": "Coach",  # Navigate to coach screen on tap
            }
            if message.context:
                data.update(message.context)

            # Send to all registered devices
            success_count = 0
            for token_info in device_tokens:
                push_token = token_info.get('push_token')
                if push_token:
                    sent = await self._send_expo_push(
                        token=push_token,
                        title=title,
                        body=message.message_text,
                        data=data
                    )
                    if sent:
                        success_count += 1

            logger.info(f"Delivered message to {success_count}/{len(device_tokens)} devices for user {message.user_id}")
            return success_count > 0

        except Exception as e:
            logger.error(f"Error delivering message immediately: {e}")
            return False

    async def get_notification_stats(self, user_id: str) -> Dict[str, Any]:
        """Get notification statistics for a user"""
        try:
            # Get message counts by type
            total_response = self.supabase.table('waiting_messages').select('id', count='exact').eq(
                'user_id', user_id
            ).execute()

            delivered_response = self.supabase.table('waiting_messages').select('id', count='exact').eq(
                'user_id', user_id
            ).eq('delivered', True).execute()

            pending_response = self.supabase.table('waiting_messages').select('id', count='exact').eq(
                'user_id', user_id
            ).eq('delivered', False).execute()

            return {
                "total_messages": total_response.count or 0,
                "delivered_messages": delivered_response.count or 0,
                "pending_messages": pending_response.count or 0,
                "last_message_at": await self._get_last_message_time(user_id)
            }

        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {
                "total_messages": 0,
                "delivered_messages": 0,
                "pending_messages": 0,
                "last_message_at": None
            }

    async def _get_last_message_time(self, user_id: str) -> Optional[str]:
        """Get timestamp of last message for user"""
        try:
            response = self.supabase.table('waiting_messages').select('created_at').eq(
                'user_id', user_id
            ).order('created_at', desc=True).limit(1).execute()

            return response.data[0]['created_at'] if response.data else None

        except Exception as e:
            logger.error(f"Error getting last message time: {e}")
            return None

    # =========================================
    # NEW: Structured Notification Methods
    # =========================================

    async def send_notification(self, payload: NotificationPayload) -> bool:
        """
        Send a push notification using the structured payload.
        Records notification in history and respects user preferences.
        """
        try:
            # Check user preferences
            if not await self._should_send_notification_type(payload.user_id, payload.type):
                logger.info(f"Notification blocked by preferences for {payload.user_id}, type: {payload.type}")
                return False

            # Get user's push tokens
            tokens = await self._get_expo_push_tokens(payload.user_id)
            if not tokens:
                logger.warning(f"No push tokens for user {payload.user_id}")
                return False

            # Record notification attempt
            notification_id = await self._record_notification_history(payload, "pending")

            # Send via Expo Push API
            success = await self._send_expo_push_batch(tokens, payload)

            # Update status
            if notification_id:
                await self._update_notification_history(
                    notification_id,
                    "sent" if success else "failed"
                )

            return success

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    async def send_task_reminder(
        self,
        user_id: str,
        task_id: str,
        task_title: str,
        minutes_until_due: int
    ) -> bool:
        """Send a task reminder notification"""
        if minutes_until_due <= 0:
            body = f"Your task '{task_title}' is now due!"
        elif minutes_until_due < 60:
            body = f"Your task '{task_title}' is due in {minutes_until_due} minutes"
        else:
            hours = minutes_until_due // 60
            body = f"Your task '{task_title}' is due in {hours} hour{'s' if hours > 1 else ''}"

        return await self.send_notification(NotificationPayload(
            user_id=user_id,
            type=NotificationType.TASK_REMINDER,
            title="Task Reminder",
            body=body,
            reference_type="todo",
            reference_id=task_id,
            data={"screen": "Tasks", "task_id": task_id}
        ))

    async def send_coach_task_notification(
        self,
        user_id: str,
        task_id: str,
        task_title: str,
        coach_reasoning: Optional[str] = None
    ) -> bool:
        """Send notification when coach creates a task for the user"""
        body = f"Cora suggested a task: '{task_title}'"
        if coach_reasoning:
            body = f"{body}\n{coach_reasoning[:100]}"

        return await self.send_notification(NotificationPayload(
            user_id=user_id,
            type=NotificationType.COACH_TASK,
            title="New Task from Cora",
            body=body,
            reference_type="todo",
            reference_id=task_id,
            data={"screen": "Tasks", "task_id": task_id}
        ))

    async def send_task_overdue_nudge(self, user_id: str, overdue_tasks: List[Dict]) -> bool:
        """Send a nudge about overdue tasks"""
        if not overdue_tasks:
            return False

        if len(overdue_tasks) == 1:
            task = overdue_tasks[0]
            body = f"Hey, your task '{task['title']}' is overdue. Did you get to it?"
        else:
            body = f"You have {len(overdue_tasks)} overdue tasks. Let's get them done!"

        return await self.send_notification(NotificationPayload(
            user_id=user_id,
            type=NotificationType.COACH_NUDGE,
            title="Cora",
            body=body,
            data={"screen": "Tasks", "nudge_type": "overdue"}
        ))

    async def send_streak_alert(self, user_id: str, current_streak: int) -> bool:
        """Send a streak risk notification"""
        body = f"Don't break your {current_streak}-day streak! Check in today."

        return await self.send_notification(NotificationPayload(
            user_id=user_id,
            type=NotificationType.STREAK_ALERT,
            title="Streak at Risk",
            body=body,
            reference_type="streak",
            data={"screen": "Home"}
        ))

    async def send_insight_notification(
        self,
        user_id: str,
        insight_id: str,
        insight_title: str
    ) -> bool:
        """Send notification about a new insight"""
        return await self.send_notification(NotificationPayload(
            user_id=user_id,
            type=NotificationType.INSIGHT,
            title="New Insight",
            body=insight_title,
            reference_type="insight",
            reference_id=insight_id,
            data={"screen": "Insights", "insight_id": insight_id}
        ))

    async def schedule_task_reminders_for_user(self, user_id: str) -> int:
        """Schedule reminders for all user's tasks with due dates and reminders enabled"""
        try:
            # Get tasks with reminders enabled
            response = self.supabase.table("shared_todos").select(
                "id, title, due_date, due_time, reminder_minutes_before"
            ).eq("user_id", user_id).eq("reminder_enabled", True).in_(
                "status", ["pending", "in_progress"]
            ).execute()

            scheduled_count = 0
            now = datetime.now(timezone.utc)

            for task in response.data or []:
                due_date = task.get("due_date")
                due_time = task.get("due_time", "09:00")
                reminder_mins = task.get("reminder_minutes_before", 30)

                if not due_date:
                    continue

                # Parse due datetime
                try:
                    due_datetime = datetime.fromisoformat(f"{due_date}T{due_time}:00")
                    if due_datetime.tzinfo is None:
                        due_datetime = due_datetime.replace(tzinfo=timezone.utc)

                    reminder_time = due_datetime - timedelta(minutes=reminder_mins)

                    # Only schedule if reminder time is in the future
                    if reminder_time > now:
                        # Check if reminder already scheduled
                        existing = self.supabase.table("notification_history").select("id").eq(
                            "user_id", user_id
                        ).eq("reference_id", task["id"]).eq("type", NotificationType.TASK_REMINDER.value).eq(
                            "status", "pending"
                        ).execute()

                        if not existing.data:
                            # Schedule the reminder
                            await self._record_notification_history(
                                NotificationPayload(
                                    user_id=user_id,
                                    type=NotificationType.TASK_REMINDER,
                                    title="Task Reminder",
                                    body=f"Your task '{task['title']}' is due in {reminder_mins} minutes",
                                    reference_type="todo",
                                    reference_id=task["id"],
                                    scheduled_for=reminder_time
                                ),
                                "pending"
                            )
                            scheduled_count += 1

                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing due date for task {task['id']}: {e}")
                    continue

            return scheduled_count

        except Exception as e:
            logger.error(f"Error scheduling task reminders: {e}")
            return 0

    async def process_scheduled_notifications(self) -> int:
        """Process notifications that are scheduled for now or past"""
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Get pending scheduled notifications that are due
            response = self.supabase.table("notification_history").select(
                "*"
            ).eq("status", "pending").lte("scheduled_for", now).limit(50).execute()

            processed_count = 0
            for notif in response.data or []:
                # Create payload from history record
                payload = NotificationPayload(
                    user_id=notif["user_id"],
                    type=NotificationType(notif["type"]),
                    title=notif["title"],
                    body=notif["body"],
                    reference_type=notif.get("reference_type"),
                    reference_id=notif.get("reference_id")
                )

                # Check preferences again before sending
                if not await self._should_send_notification_type(payload.user_id, payload.type):
                    await self._update_notification_history(notif["id"], "cancelled")
                    continue

                # Get tokens and send
                tokens = await self._get_expo_push_tokens(payload.user_id)
                if tokens:
                    success = await self._send_expo_push_batch(tokens, payload)
                    await self._update_notification_history(
                        notif["id"],
                        "sent" if success else "failed"
                    )
                    if success:
                        processed_count += 1
                else:
                    await self._update_notification_history(notif["id"], "failed", "No device tokens")

            return processed_count

        except Exception as e:
            logger.error(f"Error processing scheduled notifications: {e}")
            return 0

    async def check_and_send_overdue_task_nudges(self) -> int:
        """Check for overdue tasks and send nudges"""
        try:
            today = datetime.now(timezone.utc).date().isoformat()

            # Get users with overdue tasks
            response = self.supabase.table("shared_todos").select(
                "user_id, id, title, due_date"
            ).lt("due_date", today).in_(
                "status", ["pending", "in_progress"]
            ).execute()

            # Group by user
            users_with_overdue: Dict[str, List[Dict]] = {}
            for task in response.data or []:
                uid = task["user_id"]
                if uid not in users_with_overdue:
                    users_with_overdue[uid] = []
                users_with_overdue[uid].append(task)

            nudges_sent = 0
            for user_id, tasks in users_with_overdue.items():
                # Check if we already sent an overdue nudge today
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
                existing = self.supabase.table("notification_history").select("id").eq(
                    "user_id", user_id
                ).eq("type", NotificationType.COACH_NUDGE.value).gte(
                    "created_at", today_start
                ).execute()

                if not existing.data:
                    if await self.send_task_overdue_nudge(user_id, tasks):
                        nudges_sent += 1

            return nudges_sent

        except Exception as e:
            logger.error(f"Error checking overdue tasks: {e}")
            return 0

    async def check_and_send_streak_alerts(self) -> int:
        """Check for users at risk of breaking their streak and send alerts"""
        try:
            # Get users who haven't checked in today but have an active streak
            today = datetime.now(timezone.utc).date().isoformat()

            # Get users with streaks > 0
            streaks_response = self.supabase.table("user_streaks").select(
                "user_id, current_streak, last_activity_date"
            ).gt("current_streak", 0).execute()

            alerts_sent = 0
            for streak in streaks_response.data or []:
                last_activity = streak.get("last_activity_date")

                # If last activity was before today, they're at risk
                if last_activity and last_activity < today:
                    user_id = streak["user_id"]

                    # Check if we already sent a streak alert today
                    existing = self.supabase.table("notification_history").select("id").eq(
                        "user_id", user_id
                    ).eq("type", NotificationType.STREAK_ALERT.value).gte(
                        "created_at", f"{today}T00:00:00"
                    ).execute()

                    if not existing.data:
                        if await self.send_streak_alert(user_id, streak["current_streak"]):
                            alerts_sent += 1

            return alerts_sent

        except Exception as e:
            logger.error(f"Error checking streak alerts: {e}")
            return 0

    async def get_notification_history(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get notification history for a user"""
        try:
            response = self.supabase.table("notification_history").select(
                "*"
            ).eq("user_id", user_id).order(
                "created_at", desc=True
            ).range(offset, offset + limit - 1).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error getting notification history: {e}")
            return []

    # =========================================
    # Private Helper Methods for New Features
    # =========================================

    async def _should_send_notification_type(
        self,
        user_id: str,
        notification_type: NotificationType
    ) -> bool:
        """Check if a specific notification type should be sent based on preferences"""
        try:
            # Get notification preferences
            response = self.supabase.table("notification_preferences").select(
                "*"
            ).eq("user_id", user_id).execute()

            if not response.data:
                return True  # Default to enabled if no preferences set

            prefs = response.data[0]

            # Check master toggle
            if not prefs.get("notifications_enabled", True):
                return False

            # Check category-specific toggle
            category_map = {
                NotificationType.TASK_REMINDER: "task_reminders_enabled",
                NotificationType.COACH_NUDGE: "coach_nudges_enabled",
                NotificationType.INSIGHT: "insights_enabled",
                NotificationType.STREAK_ALERT: "streak_reminders_enabled",
                NotificationType.COACH_TASK: "task_reminders_enabled",
                NotificationType.COACH_MESSAGE: "coach_nudges_enabled",
                NotificationType.PATTERN_ALERT: "insights_enabled",
                NotificationType.ACCOUNTABILITY_NUDGE: "coach_nudges_enabled",
            }

            category_key = category_map.get(notification_type)
            if category_key and not prefs.get(category_key, True):
                return False

            # Check quiet hours
            if prefs.get("quiet_hours_enabled"):
                quiet_start = prefs.get("quiet_hours_start", "22:00")
                quiet_end = prefs.get("quiet_hours_end", "08:00")

                try:
                    now_time = datetime.now().time()
                    start_time = datetime.strptime(quiet_start[:5], "%H:%M").time()
                    end_time = datetime.strptime(quiet_end[:5], "%H:%M").time()

                    # Handle overnight quiet hours
                    if start_time > end_time:
                        in_quiet = now_time >= start_time or now_time <= end_time
                    else:
                        in_quiet = start_time <= now_time <= end_time

                    if in_quiet:
                        return False
                except ValueError:
                    pass

            # Check daily limit
            max_daily = prefs.get("max_daily_notifications", 10)
            if await self._exceeded_daily_limit(user_id, max_daily):
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking notification preferences: {e}")
            return True

    async def _exceeded_daily_limit(self, user_id: str, max_daily: int) -> bool:
        """Check if user has exceeded daily notification limit"""
        try:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            response = self.supabase.table("notification_history").select(
                "id", count="exact"
            ).eq("user_id", user_id).gte("created_at", today_start).in_(
                "status", ["sent", "delivered"]
            ).execute()

            count = response.count or 0
            return count >= max_daily

        except Exception as e:
            logger.error(f"Error checking daily limit: {e}")
            return False

    async def _get_expo_push_tokens(self, user_id: str) -> List[str]:
        """Get active Expo push tokens for a user"""
        try:
            response = self.supabase.table("device_tokens").select(
                "push_token"
            ).eq("user_id", user_id).eq("active", True).execute()

            tokens = []
            for item in response.data or []:
                token = item.get("push_token")
                if token:
                    tokens.append(token)

            return tokens

        except Exception as e:
            logger.error(f"Error getting Expo push tokens: {e}")
            return []

    async def _send_expo_push_batch(
        self,
        tokens: List[str],
        payload: NotificationPayload
    ) -> bool:
        """Send push notification to multiple tokens via Expo Push API"""
        try:
            messages = [
                {
                    "to": token,
                    "title": payload.title,
                    "body": payload.body,
                    "sound": "default",
                    "badge": 1,
                    "data": {
                        "type": payload.type.value,
                        "reference_type": payload.reference_type,
                        "reference_id": payload.reference_id,
                        **(payload.data or {})
                    }
                }
                for token in tokens
            ]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=messages,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    # Check if any were successful
                    data = result.get("data", [])
                    success_count = sum(1 for d in data if d.get("status") == "ok")
                    logger.info(f"Sent {success_count}/{len(tokens)} push notifications")
                    return success_count > 0

                logger.error(f"Expo push API error: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error sending Expo push batch: {e}")
            return False

    async def _record_notification_history(
        self,
        payload: NotificationPayload,
        status: str
    ) -> Optional[str]:
        """Record a notification in history"""
        try:
            data = {
                "user_id": payload.user_id,
                "type": payload.type.value,
                "title": payload.title,
                "body": payload.body,
                "reference_type": payload.reference_type,
                "reference_id": payload.reference_id,
                "scheduled_for": payload.scheduled_for.isoformat() if payload.scheduled_for else None,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            if status == "sent":
                data["sent_at"] = datetime.now(timezone.utc).isoformat()

            response = self.supabase.table("notification_history").insert(data).execute()

            if response.data:
                return response.data[0]["id"]
            return None

        except Exception as e:
            logger.error(f"Error recording notification history: {e}")
            return None

    async def _update_notification_history(
        self,
        notification_id: str,
        status: str,
        error_message: Optional[str] = None
    ):
        """Update notification history status"""
        try:
            update_data = {"status": status}

            if status == "sent":
                update_data["sent_at"] = datetime.now(timezone.utc).isoformat()
            elif status == "delivered":
                update_data["delivered_at"] = datetime.now(timezone.utc).isoformat()
            elif status == "failed" and error_message:
                update_data["error_message"] = error_message

            self.supabase.table("notification_history").update(update_data).eq(
                "id", notification_id
            ).execute()

        except Exception as e:
            logger.error(f"Error updating notification history: {e}")


# Global notification service instance
notification_service = NotificationService()

# Background task to process delayed messages
async def process_pending_notifications():
    """Background task to process pending notifications"""
    while True:
        try:
            processed = await notification_service.process_delayed_messages()
            if processed > 0:
                logger.info(f"Processed {processed} delayed messages")

            # Wait 30 seconds before next check
            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Error in notification processing task: {e}")
            await asyncio.sleep(60)  # Wait longer on error
