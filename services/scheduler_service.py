"""
Scheduler Service
Background job scheduler for task reminders and notifications.
Uses APScheduler to run periodic jobs for processing scheduled notifications.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.services.notification_service import notification_service

logger = logging.getLogger(__name__)

_MISFIRE_GRACE_TIME = 120


class SchedulerService:
    """Background job scheduler for CoreSense notifications."""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._is_running = False

    def start(self):
        """Start the scheduler with all configured jobs."""
        if self._is_running:
            logger.warning("Scheduler already running")
            return

        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "misfire_grace_time": _MISFIRE_GRACE_TIME,
                "coalesce": True,
            },
        )

        self.scheduler.add_job(
            self._process_notifications_job,
            trigger=IntervalTrigger(minutes=1),
            id="process_notifications",
            name="Process Scheduled Notifications",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.add_job(
            self._check_overdue_tasks_job,
            trigger=IntervalTrigger(hours=1),
            id="check_overdue_tasks",
            name="Check Overdue Tasks",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.add_job(
            self._check_streak_alerts_job,
            trigger=CronTrigger(hour=20, minute=0),
            id="check_streak_alerts",
            name="Check Streak Alerts",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.add_job(
            self._reschedule_all_reminders_job,
            trigger=IntervalTrigger(minutes=15),
            id="reschedule_reminders",
            name="Reschedule Task Reminders",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.add_job(
            self._generate_daily_insights_job,
            trigger=CronTrigger(hour=10, minute=0),
            id="daily_insights",
            name="Daily Insight Generation",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.add_job(
            self._send_coach_nudges_job,
            trigger=CronTrigger(hour=14, minute=0),
            id="coach_nudges",
            name="Coach Nudges",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("Scheduler started with notification jobs")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler and self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Scheduler stopped")

    async def _process_notifications_job(self):
        """Job: Process all due scheduled notifications."""
        try:
            count = await notification_service.process_scheduled_notifications()
            if count > 0:
                logger.info(f"Processed {count} scheduled notifications")
        except Exception as e:
            logger.error(f"Error in process_notifications job: {e}")

    async def _check_overdue_tasks_job(self):
        """Job: Check for overdue tasks and send nudges."""
        try:
            count = await notification_service.check_and_send_overdue_task_nudges()
            if count > 0:
                logger.info(f"Sent {count} overdue task nudges")
        except Exception as e:
            logger.error(f"Error in check_overdue_tasks job: {e}")

    async def _check_streak_alerts_job(self):
        """Job: Check for users at risk of breaking streaks."""
        try:
            count = await notification_service.check_and_send_streak_alerts()
            if count > 0:
                logger.info(f"Sent {count} streak alerts")
        except Exception as e:
            logger.error(f"Error in check_streak_alerts job: {e}")

    async def _reschedule_all_reminders_job(self):
        """Job: Reschedule reminders for all users with pending tasks."""
        try:
            from backend.database.supabase_client import get_supabase_client, with_retry

            def _query():
                sb = get_supabase_client()
                return sb.table("shared_todos").select(
                    "user_id"
                ).eq("reminder_enabled", True).in_(
                    "status", ["pending", "in_progress"]
                ).execute()

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, _query)

            user_ids = set(task["user_id"] for task in response.data or [])

            total_scheduled = 0
            for user_id in user_ids:
                count = await notification_service.schedule_task_reminders_for_user(user_id)
                total_scheduled += count

            if total_scheduled > 0:
                logger.info(f"Rescheduled {total_scheduled} task reminders for {len(user_ids)} users")

        except Exception as e:
            logger.error(f"Error in reschedule_reminders job: {e}")

    async def _get_users_with_tokens(self) -> list[str]:
        """Get user IDs that have at least one active device token."""
        from backend.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        response = sb.table("device_tokens").select(
            "user_id"
        ).eq("active", True).execute()

        return list({row["user_id"] for row in response.data or []})

    async def _generate_daily_insights_job(self):
        """Job: Generate insights for active users and push top actionable one."""
        try:
            from backend.services.insight_generation_service import insight_generation_service
            from backend.database.supabase_client import get_supabase_client
            from backend.routers.app_api import persist_generated_insights

            user_ids = await self._get_users_with_tokens()
            logger.info(f"Daily insights: processing {len(user_ids)} users")

            generated_count = 0
            notified_count = 0

            for user_id in user_ids:
                try:
                    insights = await insight_generation_service.generate_insights(user_id, "weekly")
                    if not insights:
                        continue

                    # Persist insights to DB
                    new_ids = await persist_generated_insights(user_id, insights)
                    generated_count += len(new_ids)

                    # Send push for the top actionable insight
                    if new_ids:
                        actionable = [i for i in insights if i.get("actionable")]
                        if actionable:
                            top = max(actionable, key=lambda x: x.get("priority", 0))
                        else:
                            top = insights[0]

                        sent = await notification_service.send_insight_notification(
                            user_id=user_id,
                            insight_id=new_ids[0],
                            insight_title=top.get("body", top.get("title", "New insight available"))
                        )
                        if sent:
                            notified_count += 1

                except Exception as e:
                    logger.warning(f"Error generating insights for {user_id}: {e}")

            logger.info(f"Daily insights: generated {generated_count}, notified {notified_count}")

        except Exception as e:
            logger.error(f"Error in daily_insights job: {e}")

    async def _send_coach_nudges_job(self):
        """Job: Send contextual coach nudges to eligible users."""
        try:
            from backend.services.nudge_service import nudge_service

            user_ids = await self._get_users_with_tokens()
            logger.info(f"Coach nudges: checking {len(user_ids)} users")

            sent_count = 0

            for user_id in user_ids:
                try:
                    result = await nudge_service.generate_nudge(user_id)
                    if result is None:
                        continue

                    title, body = result
                    sent = await notification_service.send_coach_nudge(user_id, title, body)
                    if sent:
                        sent_count += 1

                except Exception as e:
                    logger.warning(f"Error sending nudge to {user_id}: {e}")

            logger.info(f"Coach nudges: sent {sent_count}")

        except Exception as e:
            logger.error(f"Error in coach_nudges job: {e}")


# Global scheduler instance
scheduler_service = SchedulerService()
