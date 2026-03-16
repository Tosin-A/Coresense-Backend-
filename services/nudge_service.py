"""
Nudge Service
Generates contextual, varied coach nudge messages 2-3x per week.
Template-based (no LLM) with randomness to feel human.
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Message templates by condition
_ABSENT_MESSAGES = [
    ("Cora", "Haven't heard from you in a bit — how's everything going?"),
    ("Cora", "It's been a couple days. Just checking in — everything okay?"),
    ("Cora", "Hey, no pressure. Just wanted to see how you're doing."),
    ("Cora", "Miss you around here. How are things?"),
    ("Cora", "Been a little quiet — hope that means things are good."),
]

_HIGH_STREAK_MESSAGES = [
    ("Nice streak!", "{streak}-day streak and counting. What's been working for you?"),
    ("Keep it up!", "You've been on a {streak}-day streak — what's keeping you going?"),
    ("Consistency wins", "{streak} days in a row. That's real momentum."),
    ("On a roll", "Day {streak} of showing up. You should feel good about that."),
]

_LOW_MOOD_MESSAGES = [
    ("Cora", "Noticed things have been tough. One small win today is enough."),
    ("Cora", "Rough patch? That's okay. What's one thing you can do for yourself today?"),
    ("Cora", "It's okay to have off days. What would help you feel a little better right now?"),
    ("Cora", "Be gentle with yourself today. Even small steps count."),
]

_GOOD_PROGRESS_MESSAGES = [
    ("Solid work", "You knocked out {tasks} tasks this week. Keep that energy."),
    ("Making moves", "{tasks} tasks done — you're building real momentum."),
    ("Nice progress", "Look at that — {tasks} tasks checked off. You're in a groove."),
    ("Getting it done", "{tasks} tasks completed. That focus is paying off."),
]

_GENERAL_MESSAGES = [
    ("Cora", "Quick thought: even 5 minutes of movement can shift your day."),
    ("Cora", "What's one thing you're looking forward to today?"),
    ("Cora", "Take a breath. You're doing better than you think."),
    ("Cora", "Small reminder: hydration matters. Grab some water."),
    ("Cora", "What went well yesterday? Sometimes it helps to look back."),
    ("Cora", "You don't have to do everything today. Just pick one thing."),
]


class NudgeService:
    """Generates contextual nudge messages with natural variety."""

    @property
    def supabase(self):
        return get_supabase_client()

    def should_nudge_today(self, user_id: str) -> bool:
        """
        Deterministic check: should this user get a nudge today?
        Picks 2-3 days per week per user, spread out so not all users
        get nudged simultaneously.
        """
        now = datetime.now(timezone.utc)
        week_number = now.isocalendar()[1]
        day_of_week = now.weekday()  # 0=Mon ... 6=Sun

        # Hash user_id + week to get a stable per-user-per-week seed
        seed_str = f"{user_id}:{week_number}:{now.year}"
        seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)

        rng = random.Random(seed)

        # Pick 2 or 3 days from Mon-Sat (0-5), skip Sunday
        num_days = rng.choice([2, 2, 3])  # Slightly favor 2
        nudge_days = sorted(rng.sample(range(6), num_days))

        return day_of_week in nudge_days

    async def generate_nudge(self, user_id: str) -> Optional[Tuple[str, str]]:
        """
        Generate a contextual nudge for the user.
        Returns (title, body) or None if nudge not needed today.
        """
        if not self.should_nudge_today(user_id):
            return None

        try:
            context = await self._gather_context(user_id)
            return self._pick_message(user_id, context)
        except Exception as e:
            logger.error(f"Error generating nudge for {user_id}: {e}")
            return None

    async def _gather_context(self, user_id: str) -> Dict:
        """Gather user context for nudge selection."""
        context: Dict = {
            "days_since_last_checkin": None,
            "current_streak": 0,
            "recent_mood_avg": None,
            "tasks_completed_week": 0,
            "pending_task_count": 0,
        }

        try:
            # Last message timestamp
            msg_resp = self.supabase.table("messages").select(
                "created_at"
            ).eq("user_id", user_id).order(
                "created_at", desc=True
            ).limit(1).execute()

            if msg_resp.data:
                last_msg = datetime.fromisoformat(
                    msg_resp.data[0]["created_at"].replace("Z", "+00:00")
                )
                delta = datetime.now(timezone.utc) - last_msg
                context["days_since_last_checkin"] = delta.days
        except Exception as e:
            logger.warning(f"Error fetching last checkin for {user_id}: {e}")

        try:
            # Current streak
            streak_resp = self.supabase.table("user_streaks").select(
                "current_streak"
            ).eq("user_id", user_id).limit(1).execute()

            if streak_resp.data:
                context["current_streak"] = streak_resp.data[0].get("current_streak", 0)
        except Exception as e:
            logger.warning(f"Error fetching streak for {user_id}: {e}")

        try:
            # Recent mood (last 3 days from health_metrics)
            three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            mood_resp = self.supabase.table("health_metrics").select(
                "value"
            ).eq("user_id", user_id).eq(
                "metric_type", "mood"
            ).gte("recorded_at", three_days_ago).execute()

            if mood_resp.data and len(mood_resp.data) >= 2:
                values = [float(m["value"]) for m in mood_resp.data if m.get("value")]
                if values:
                    context["recent_mood_avg"] = sum(values) / len(values)
        except Exception as e:
            logger.warning(f"Error fetching mood for {user_id}: {e}")

        try:
            # Tasks completed this week
            week_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            tasks_resp = self.supabase.table("shared_todos").select(
                "id", count="exact"
            ).eq("user_id", user_id).eq(
                "status", "completed"
            ).gte("updated_at", week_start).execute()

            context["tasks_completed_week"] = tasks_resp.count or 0
        except Exception as e:
            logger.warning(f"Error fetching completed tasks for {user_id}: {e}")

        try:
            # Pending tasks
            pending_resp = self.supabase.table("shared_todos").select(
                "id", count="exact"
            ).eq("user_id", user_id).in_(
                "status", ["pending", "in_progress"]
            ).execute()

            context["pending_task_count"] = pending_resp.count or 0
        except Exception as e:
            logger.warning(f"Error fetching pending tasks for {user_id}: {e}")

        return context

    def _pick_message(self, user_id: str, context: Dict) -> Tuple[str, str]:
        """Pick a message based on context, with variety via seeded random."""
        # Seed with user_id + date for daily variety but reproducibility
        today = datetime.now(timezone.utc).date().isoformat()
        seed = int(hashlib.sha256(f"{user_id}:{today}:nudge".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        days_absent = context.get("days_since_last_checkin")
        streak = context.get("current_streak", 0)
        mood = context.get("recent_mood_avg")
        tasks_done = context.get("tasks_completed_week", 0)

        # Build weighted candidate pool
        candidates: List[Tuple[str, str]] = []

        if days_absent is not None and days_absent >= 2:
            candidates.extend(_ABSENT_MESSAGES)

        if streak >= 7:
            formatted = [
                (t, b.format(streak=streak)) for t, b in _HIGH_STREAK_MESSAGES
            ]
            candidates.extend(formatted)

        if mood is not None and mood < 3.0:
            candidates.extend(_LOW_MOOD_MESSAGES)

        if tasks_done >= 3:
            formatted = [
                (t, b.format(tasks=tasks_done)) for t, b in _GOOD_PROGRESS_MESSAGES
            ]
            candidates.extend(formatted)

        # Always include some general messages for variety
        candidates.extend(_GENERAL_MESSAGES)

        return rng.choice(candidates)


nudge_service = NudgeService()
