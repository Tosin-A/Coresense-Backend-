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

        self.scheduler = AsyncIOScheduler(timezone="UTC")

        # Job 1: Process scheduled notifications every minute
        # This sends task reminders that are due
        self.scheduler.add_job(
            self._process_notifications_job,
            trigger=IntervalTrigger(minutes=1),
            id="process_notifications",
            name="Process Scheduled Notifications",
            replace_existing=True,
            max_instances=1,
        )

        # Job 2: Check for overdue tasks every hour and send nudges
        self.scheduler.add_job(
            self._check_overdue_tasks_job,
            trigger=IntervalTrigger(hours=1),
            id="check_overdue_tasks",
            name="Check Overdue Tasks",
            replace_existing=True,
            max_instances=1,
        )

        # Job 3: Check streak alerts daily at 8 PM UTC
        self.scheduler.add_job(
            self._check_streak_alerts_job,
            trigger=CronTrigger(hour=20, minute=0),
            id="check_streak_alerts",
            name="Check Streak Alerts",
            replace_existing=True,
            max_instances=1,
        )

        # Job 4: Schedule all task reminders for all users every 15 minutes
        # This catches any reminders that weren't scheduled at creation time
        self.scheduler.add_job(
            self._reschedule_all_reminders_job,
            trigger=IntervalTrigger(minutes=15),
            id="reschedule_reminders",
            name="Reschedule Task Reminders",
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
            from backend.database.supabase_client import get_supabase_client

            supabase = get_supabase_client()

            # Get all unique users with reminder-enabled tasks
            response = supabase.table("shared_todos").select(
                "user_id"
            ).eq("reminder_enabled", True).in_(
                "status", ["pending", "in_progress"]
            ).execute()

            user_ids = set(task["user_id"] for task in response.data or [])

            total_scheduled = 0
            for user_id in user_ids:
                count = await notification_service.schedule_task_reminders_for_user(user_id)
                total_scheduled += count

            if total_scheduled > 0:
                logger.info(f"Rescheduled {total_scheduled} task reminders for {len(user_ids)} users")

        except Exception as e:
            logger.error(f"Error in reschedule_reminders job: {e}")


# Global scheduler instance
scheduler_service = SchedulerService()
