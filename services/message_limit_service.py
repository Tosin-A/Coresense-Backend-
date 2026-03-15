"""
Message Limit Service
Daily/weekly message limits.

Free: 10 messages/day, 25 messages/week
Pro: 10 messages/day, 30 messages/week (IAP only)
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import logging

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Limit configuration
FREE_DAILY_LIMIT = 10
FREE_WEEKLY_LIMIT = 25
PRO_DAILY_LIMIT = 25
PRO_WEEKLY_LIMIT = 60


def _needs_daily_reset(last_reset: Optional[str]) -> bool:
    """Check if daily counter needs resetting (new UTC day)."""
    if not last_reset:
        return True
    try:
        last = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return last.date() < now.date()
    except (ValueError, AttributeError):
        return True


def _needs_weekly_reset(last_reset: Optional[str]) -> bool:
    """Check if weekly counter needs resetting (new ISO week)."""
    if not last_reset:
        return True
    try:
        last = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return last.isocalendar()[1] != now.isocalendar()[1] or last.year != now.year
    except (ValueError, AttributeError):
        return True


def get_user_message_limit(user_id: str) -> Dict[str, Any]:
    """
    Get or create message limits for a user.
    Automatically resets daily/weekly counters when periods roll over.
    """
    client = get_supabase_client()

    try:
        response = client.table("user_message_limits")\
            .select("*")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()

        if response.data and len(response.data) > 0:
            record = response.data[0]
            updates = {}

            # Auto-reset daily counter
            if _needs_daily_reset(record.get('last_daily_reset')):
                updates['daily_messages_used'] = 0
                updates['last_daily_reset'] = datetime.now(timezone.utc).isoformat()

            # Auto-reset weekly counter
            if _needs_weekly_reset(record.get('last_weekly_reset')):
                updates['weekly_messages_used'] = 0
                updates['last_weekly_reset'] = datetime.now(timezone.utc).isoformat()

            if updates:
                client.table("user_message_limits")\
                    .update(updates)\
                    .eq("user_id", user_id)\
                    .execute()
                record.update(updates)

            return record

        # Create default limits for new user
        is_pro = False
        new_record = {
            "user_id": user_id,
            "messages_limit": FREE_DAILY_LIMIT,
            "messages_used": 0,
            "daily_messages_used": 0,
            "weekly_messages_used": 0,
            "daily_limit": FREE_DAILY_LIMIT,
            "weekly_limit": FREE_WEEKLY_LIMIT,
            "is_pro": is_pro,
            "last_daily_reset": datetime.now(timezone.utc).isoformat(),
            "last_weekly_reset": datetime.now(timezone.utc).isoformat(),
        }
        response = client.table("user_message_limits")\
            .insert(new_record)\
            .execute()

        if response.data and len(response.data) > 0:
            return response.data[0]

        return new_record

    except Exception as e:
        logger.error(f"Error getting/creating message limits for user {user_id}: {e}", exc_info=True)
        return {
            "user_id": user_id,
            "messages_used": 0,
            "daily_messages_used": 0,
            "weekly_messages_used": 0,
            "daily_limit": FREE_DAILY_LIMIT,
            "weekly_limit": FREE_WEEKLY_LIMIT,
            "is_pro": False,
        }


def check_message_limit(user_id: str) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Check if user can send another message.

    Returns:
        Tuple of (allowed, reason, limits)
        reason: None if allowed, "daily_limit_reached" or "weekly_limit_reached" if not
    """
    try:
        limits = get_user_message_limit(user_id)

        daily_limit = limits.get('daily_limit', FREE_DAILY_LIMIT)
        weekly_limit = limits.get('weekly_limit', FREE_WEEKLY_LIMIT)
        daily_used = limits.get('daily_messages_used', 0)
        weekly_used = limits.get('weekly_messages_used', 0)

        if daily_used >= daily_limit:
            return False, "daily_limit_reached", limits

        if weekly_used >= weekly_limit:
            return False, "weekly_limit_reached", limits

        return True, None, limits

    except Exception as e:
        logger.error(f"Error checking message limits for user {user_id}: {e}", exc_info=True)
        # Fail open
        return True, None, {}


def increment_message_count(user_id: str) -> bool:
    """Increment both daily and weekly message counts after a successful message."""
    try:
        limits = get_user_message_limit(user_id)
        client = get_supabase_client()

        new_daily = limits.get('daily_messages_used', 0) + 1
        new_weekly = limits.get('weekly_messages_used', 0) + 1
        new_total = limits.get('messages_used', 0) + 1

        response = client.table("user_message_limits")\
            .update({
                "daily_messages_used": new_daily,
                "weekly_messages_used": new_weekly,
                "messages_used": new_total,
            })\
            .eq("user_id", user_id)\
            .execute()

        if response.data and len(response.data) > 0:
            logger.info(f"Message count incremented for user {user_id}: daily={new_daily}, weekly={new_weekly}")
            return True

        return False

    except Exception as e:
        logger.error(f"Failed to increment message count for user {user_id}: {e}", exc_info=True)
        return False


def get_user_usage_stats(user_id: str) -> Dict[str, Any]:
    """Get user's message usage statistics with daily/weekly breakdown."""
    try:
        limits = get_user_message_limit(user_id)

        daily_limit = limits.get('daily_limit', FREE_DAILY_LIMIT)
        weekly_limit = limits.get('weekly_limit', FREE_WEEKLY_LIMIT)
        daily_used = limits.get('daily_messages_used', 0)
        weekly_used = limits.get('weekly_messages_used', 0)

        daily_remaining = max(0, daily_limit - daily_used)
        weekly_remaining = max(0, weekly_limit - weekly_used)
        # The effective remaining is the minimum of both
        messages_remaining = min(daily_remaining, weekly_remaining)

        return {
            "messages_used": limits.get('messages_used', 0),
            "messages_limit": daily_limit,
            "messages_remaining": messages_remaining,
            "daily_used": daily_used,
            "daily_limit": daily_limit,
            "daily_remaining": daily_remaining,
            "weekly_used": weekly_used,
            "weekly_limit": weekly_limit,
            "weekly_remaining": weekly_remaining,
            "usage_percentage": min(100.0, (daily_used / daily_limit) * 100) if daily_limit > 0 else 0,
            "limit_type": (
                "daily" if daily_used >= daily_limit
                else "weekly" if weekly_used >= weekly_limit
                else None
            ),
        }

    except Exception as e:
        logger.error(f"Failed to get usage stats for user {user_id}: {e}", exc_info=True)
        return {
            "messages_used": 0,
            "messages_limit": FREE_DAILY_LIMIT,
            "messages_remaining": FREE_DAILY_LIMIT,
            "daily_used": 0,
            "daily_limit": FREE_DAILY_LIMIT,
            "daily_remaining": FREE_DAILY_LIMIT,
            "weekly_used": 0,
            "weekly_limit": FREE_WEEKLY_LIMIT,
            "weekly_remaining": FREE_WEEKLY_LIMIT,
            "usage_percentage": 0.0,
            "limit_type": None,
        }


def upgrade_to_pro(user_id: str) -> bool:
    """Upgrade user to Pro limits (10/day, 30/week). Called when subscription activates."""
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .update({
                "is_pro": True,
                "daily_limit": PRO_DAILY_LIMIT,
                "weekly_limit": PRO_WEEKLY_LIMIT,
                "pro_upgraded_at": datetime.now(timezone.utc).isoformat(),
            })\
            .eq("user_id", user_id)\
            .execute()

        if response.data and len(response.data) > 0:
            logger.info("Upgraded user %s to Pro limits (%d/day, %d/week)", user_id, PRO_DAILY_LIMIT, PRO_WEEKLY_LIMIT)
            return True

        # User may not have a row yet; ensure one exists
        get_user_message_limit(user_id)
        return upgrade_to_pro(user_id)
    except Exception as e:
        logger.error("Failed to upgrade user %s to Pro: %s", user_id, e, exc_info=True)
        return False


def downgrade_from_pro(user_id: str) -> bool:
    """Downgrade user to free limits (5/day, 15/week). Called when subscription ends."""
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .update({
                "is_pro": False,
                "daily_limit": FREE_DAILY_LIMIT,
                "weekly_limit": FREE_WEEKLY_LIMIT,
                "pro_upgraded_at": None,
            })\
            .eq("user_id", user_id)\
            .execute()

        success = response.data and len(response.data) > 0
        if success:
            logger.info("Downgraded user %s to free limits (%d/day, %d/week)", user_id, FREE_DAILY_LIMIT, FREE_WEEKLY_LIMIT)
        return success
    except Exception as e:
        logger.error("Failed to downgrade user %s from Pro: %s", user_id, e, exc_info=True)
        return False


def reset_message_limits(user_id: str) -> bool:
    """Reset message limits for a user (admin function)."""
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .update({
                "messages_used": 0,
                "daily_messages_used": 0,
                "weekly_messages_used": 0,
                "is_pro": False,
                "daily_limit": FREE_DAILY_LIMIT,
                "weekly_limit": FREE_WEEKLY_LIMIT,
                "pro_upgraded_at": None,
                "last_daily_reset": datetime.now(timezone.utc).isoformat(),
                "last_weekly_reset": datetime.now(timezone.utc).isoformat(),
            })\
            .eq("user_id", user_id)\
            .execute()

        success = len(response.data) > 0 if response.data else False
        if success:
            logger.info(f"Reset message limits for user {user_id}")
        return success

    except Exception as e:
        logger.error(f"Failed to reset message limits for user {user_id}: {e}", exc_info=True)
        return False


def get_all_user_stats() -> Dict[str, Any]:
    """Get statistics for all users (admin function)."""
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .select("messages_used, daily_messages_used, weekly_messages_used, is_pro")\
            .execute()

        if not response.data:
            return {
                "total_users": 0,
                "free_users": 0,
                "pro_users": 0,
                "total_messages_sent": 0,
                "average_messages_per_user": 0.0
            }

        users = response.data
        total_users = len(users)
        free_users = len([u for u in users if not u.get('is_pro', False)])
        pro_users = total_users - free_users
        total_messages_sent = sum(u.get('messages_used', 0) for u in users)
        average_messages_per_user = total_messages_sent / total_users if total_users > 0 else 0.0

        return {
            "total_users": total_users,
            "free_users": free_users,
            "pro_users": pro_users,
            "total_messages_sent": total_messages_sent,
            "average_messages_per_user": round(average_messages_per_user, 2)
        }

    except Exception as e:
        logger.error(f"Failed to get all user stats: {e}", exc_info=True)
        return {
            "total_users": 0,
            "free_users": 0,
            "pro_users": 0,
            "total_messages_sent": 0,
            "average_messages_per_user": 0.0
        }
