"""
Message Limit Service
Handles 10-message limit for free users with pro upgrade functionality
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MESSAGE_LIMIT = 10

def get_user_message_limit(user_id: str) -> Dict[str, Any]:
    """
    Get or create message limits for a user.
    
    Args:
        user_id: User ID to get limits for
        
    Returns:
        Dict with message limit information
        
    Raises:
        Exception: If failed to create user message limits
    """
    client = get_supabase_client()
    
    try:
        # Try to get existing limits
        response = client.table("user_message_limits")\
            .select("*")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        # Create default limits for new user
        logger.info(f"Creating default message limits for user {user_id}")
        response = client.table("user_message_limits")\
            .insert({
                "user_id": user_id,
                "messages_limit": DEFAULT_MESSAGE_LIMIT,
                "messages_used": 0,
                "is_pro": False
            })\
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        raise Exception("Failed to create user message limits")
        
    except Exception as e:
        logger.error(f"Error getting/creating message limits for user {user_id}: {e}", exc_info=True)
        # Return default limits as fallback
        return {
            "user_id": user_id,
            "messages_used": 0,
            "messages_limit": DEFAULT_MESSAGE_LIMIT,
            "is_pro": False,
            "pro_upgraded_at": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

def check_message_limit(user_id: str) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Check if user can send another message.
    
    Args:
        user_id: User ID to check
        
    Returns:
        Tuple of (allowed: bool, reason: Optional[str], limits: Dict[str, Any])
        Reason will be:
        - None if allowed
        - "message_limit_reached" if limit exceeded
        - "user_not_found" if user doesn't exist
    """
    try:
        limits = get_user_message_limit(user_id)
        
        # Pro users have unlimited messages
        if limits.get('is_pro', False):
            return True, None, limits
        
        messages_used = limits.get('messages_used', 0)
        messages_limit = limits.get('messages_limit', DEFAULT_MESSAGE_LIMIT)
        
        if messages_used >= messages_limit:
            return False, "message_limit_reached", limits
        
        return True, None, limits
        
    except Exception as e:
        logger.error(f"Error checking message limits for user {user_id}: {e}", exc_info=True)
        # Fail open - allow the message but log error
        return True, None, {}

def increment_message_count(user_id: str) -> bool:
    """
    Increment message count for a user after successful message processing.
    
    Args:
        user_id: User ID to update
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        limits = get_user_message_limit(user_id)
        
        # Don't increment for pro users
        if limits.get('is_pro', False):
            return True
        
        client = get_supabase_client()
        new_count = limits.get('messages_used', 0) + 1
        
        response = client.table("user_message_limits")\
            .update({
                "messages_used": new_count
            })\
            .eq("user_id", user_id)\
            .execute()
        
        if response.data and len(response.data) > 0:
            logger.info(f"Incremented message count for user {user_id}: {new_count}")
            return True
        else:
            logger.error(f"Failed to increment message count for user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to increment message count for user {user_id}: {e}", exc_info=True)
        return False

def upgrade_to_pro(user_id: str) -> bool:
    """
    Upgrade user to pro plan (unlimited messages).
    
    Args:
        user_id: User ID to upgrade
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .update({
                "is_pro": True,
                "pro_upgraded_at": datetime.now().isoformat()
            })\
            .eq("user_id", user_id)\
            .execute()
        
        success = len(response.data) > 0 if response.data else False
        
        if success:
            logger.info(f"Successfully upgraded user {user_id} to pro plan")
        else:
            logger.error(f"Failed to upgrade user {user_id} to pro plan")
            
        return success
        
    except Exception as e:
        logger.error(f"Failed to upgrade user {user_id} to pro: {e}", exc_info=True)
        return False

def get_user_usage_stats(user_id: str) -> Dict[str, Any]:
    """
    Get user's message usage statistics.
    
    Args:
        user_id: User ID to get stats for
        
    Returns:
        Dict with usage statistics
    """
    try:
        limits = get_user_message_limit(user_id)
        
        messages_used = limits.get('messages_used', 0)
        messages_limit = limits.get('messages_limit', DEFAULT_MESSAGE_LIMIT)
        is_pro = limits.get('is_pro', False)
        
        return {
            "messages_used": messages_used,
            "messages_limit": messages_limit,
            "is_pro": is_pro,
            "messages_remaining": (
                float('inf') if is_pro else max(0, messages_limit - messages_used)
            ),
            "pro_upgraded_at": limits.get('pro_upgraded_at'),
            "usage_percentage": (
                100.0 if is_pro else min(100.0, (messages_used / messages_limit) * 100)
            )
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage stats for user {user_id}: {e}", exc_info=True)
        return {
            "messages_used": 0,
            "messages_limit": DEFAULT_MESSAGE_LIMIT,
            "is_pro": False,
            "messages_remaining": DEFAULT_MESSAGE_LIMIT,
            "pro_upgraded_at": None,
            "usage_percentage": 0.0
        }

def reset_message_limits(user_id: str) -> bool:
    """
    Reset message limits for a user (admin function).
    
    Args:
        user_id: User ID to reset
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .update({
                "messages_used": 0,
                "is_pro": False,
                "pro_upgraded_at": None
            })\
            .eq("user_id", user_id)\
            .execute()
        
        success = len(response.data) > 0 if response.data else False
        
        if success:
            logger.info(f"Reset message limits for user {user_id}")
        else:
            logger.error(f"Failed to reset message limits for user {user_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Failed to reset message limits for user {user_id}: {e}", exc_info=True)
        return False

def get_all_user_stats() -> Dict[str, Any]:
    """
    Get statistics for all users (admin function).
    
    Returns:
        Dict with overall usage statistics
    """
    try:
        client = get_supabase_client()
        response = client.table("user_message_limits")\
            .select("messages_used, messages_limit, is_pro")\
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
