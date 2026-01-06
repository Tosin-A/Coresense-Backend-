"""
Cost control service.
Tracks AI calls, enforces limits, and manages usage quotas.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone, date
import logging
import hashlib

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Default limits (can be overridden per user)
DEFAULT_DAILY_AI_CALLS = 100
DEFAULT_MONTHLY_AI_CALLS = 3000
DEFAULT_DAILY_TOKENS = 50000

# Safety boundaries
MAX_TOKENS_PER_CALL = 200  # Maximum tokens per AI generation
MAX_MESSAGE_LENGTH = 1000  # Maximum message length in characters
MIN_TIME_BETWEEN_CALLS = 1  # Minimum seconds between AI calls for same user


def get_user_cost_limits(user_id: str) -> Dict[str, Any]:
    """
    Get or create cost limits for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        Dict with cost limit information
    """
    client = get_supabase_client()
    
    # Try to get existing limits
    response = client.table("user_cost_limits")\
        .select("*")\
        .eq("user_id", user_id)\
        .limit(1)\
        .execute()
    
    if response.data and len(response.data) > 0:
        limits = response.data[0]
        
        # Reset daily limits if needed
        last_reset = datetime.fromisoformat(limits['last_reset_date']).date() if limits.get('last_reset_date') else date.today()
        if last_reset < date.today():
            reset_daily_limits(user_id)
            # Fetch again after reset
            response = client.table("user_cost_limits")\
                .select("*")\
                .eq("user_id", user_id)\
                .limit(1)\
                .execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
        
        return limits
    
    # Create default limits
    response = client.table("user_cost_limits")\
        .insert({
            "user_id": user_id,
            "daily_ai_calls_limit": DEFAULT_DAILY_AI_CALLS,
            "monthly_ai_calls_limit": DEFAULT_MONTHLY_AI_CALLS,
            "daily_tokens_limit": DEFAULT_DAILY_TOKENS,
            "last_reset_date": date.today().isoformat()
        })\
        .execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    
    raise Exception("Failed to create user cost limits")


def reset_daily_limits(user_id: str) -> None:
    """Reset daily usage counters for a user."""
    client = get_supabase_client()
    client.table("user_cost_limits")\
        .update({
            "daily_ai_calls_used": 0,
            "daily_tokens_used": 0,
            "last_reset_date": date.today().isoformat()
        })\
        .eq("user_id", user_id)\
        .execute()


def check_ai_call_allowed(user_id: str, estimated_tokens: int = 150) -> Tuple[bool, Optional[str]]:
    """
    Check if an AI call is allowed for a user.
    
    Args:
        user_id: User ID
        estimated_tokens: Estimated tokens for this call
        
    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
    """
    try:
        limits = get_user_cost_limits(user_id)
        
        # Check if user is blocked
        if limits.get('is_blocked', False):
            return False, limits.get('block_reason', 'User is blocked')
        
        # Check daily AI calls limit
        daily_calls_used = limits.get('daily_ai_calls_used', 0)
        daily_calls_limit = limits.get('daily_ai_calls_limit', DEFAULT_DAILY_AI_CALLS)
        if daily_calls_used >= daily_calls_limit:
            return False, f"Daily AI call limit reached ({daily_calls_limit} calls)"
        
        # Check monthly AI calls limit
        monthly_calls_used = limits.get('monthly_ai_calls_used', 0)
        monthly_calls_limit = limits.get('monthly_ai_calls_limit', DEFAULT_MONTHLY_AI_CALLS)
        if monthly_calls_used >= monthly_calls_limit:
            return False, f"Monthly AI call limit reached ({monthly_calls_limit} calls)"
        
        # Check daily tokens limit
        daily_tokens_used = limits.get('daily_tokens_used', 0)
        daily_tokens_limit = limits.get('daily_tokens_limit', DEFAULT_DAILY_TOKENS)
        if daily_tokens_used + estimated_tokens > daily_tokens_limit:
            return False, f"Daily token limit would be exceeded ({daily_tokens_limit} tokens)"
        
        # Check safety boundaries
        if estimated_tokens > MAX_TOKENS_PER_CALL:
            return False, f"Requested tokens ({estimated_tokens}) exceeds maximum per call ({MAX_TOKENS_PER_CALL})"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Error checking AI call limits: {e}", exc_info=True)
        # Fail open for now (allow the call) but log the error
        return True, None


def record_ai_call(
    user_id: str,
    call_type: str,
    tokens_generated: int,
    tokens_input: int = 0,
    success: bool = True,
    response_time_ms: Optional[int] = None,
    error_message: Optional[str] = None,
    cached: bool = False,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Record an AI call for cost tracking.
    
    Args:
        user_id: User ID
        call_type: Type of call ('message_generation', 'memory_summarization', 'insight_generation')
        tokens_generated: Number of tokens generated
        tokens_input: Number of input tokens
        success: Whether the call was successful
        response_time_ms: Response time in milliseconds
        error_message: Error message if failed
        cached: Whether response was from cache
        metadata: Additional metadata
    """
    client = get_supabase_client()
    
    try:
        # Log the call
        client.table("ai_call_logs")\
            .insert({
                "user_id": user_id,
                "call_type": call_type,
                "tokens_generated": tokens_generated,
                "tokens_input": tokens_input,
                "model_path": "mlx-community/Llama-3.2-3B-Instruct",
                "response_time_ms": response_time_ms,
                "success": success,
                "error_message": error_message,
                "cached": cached,
                "metadata": metadata or {}
            })\
            .execute()
        
        # Update user cost limits (only if successful and not cached)
        if success and not cached:
            # Get current limits
            limits = get_user_cost_limits(user_id)
            
            # Calculate new usage
            new_daily_calls = limits.get('daily_ai_calls_used', 0) + 1
            new_monthly_calls = limits.get('monthly_ai_calls_used', 0) + 1
            new_daily_tokens = limits.get('daily_tokens_used', 0) + tokens_generated
            
            # Update limits
            client.table("user_cost_limits")\
                .update({
                    "daily_ai_calls_used": new_daily_calls,
                    "monthly_ai_calls_used": new_monthly_calls,
                    "daily_tokens_used": new_daily_tokens
                })\
                .eq("user_id", user_id)\
                .execute()
            
            logger.info(f"Recorded AI call for user {user_id}: {tokens_generated} tokens, {call_type}")
        
    except Exception as e:
        logger.error(f"Failed to record AI call: {e}", exc_info=True)
        # Don't fail the request if logging fails


def get_user_usage_stats(user_id: str, days: int = 7) -> Dict[str, Any]:
    """
    Get usage statistics for a user.
    
    Args:
        user_id: User ID
        days: Number of days to look back
        
    Returns:
        Dict with usage statistics
    """
    client = get_supabase_client()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    try:
        # Get call logs
        logs_response = client.table("ai_call_logs")\
            .select("*")\
            .eq("user_id", user_id)\
            .gte("created_at", cutoff_date)\
            .execute()
        
        logs = logs_response.data if logs_response.data else []
        
        # Calculate stats
        total_calls = len(logs)
        successful_calls = len([l for l in logs if l.get('success', True)])
        cached_calls = len([l for l in logs if l.get('cached', False)])
        total_tokens = sum(l.get('tokens_generated', 0) for l in logs)
        avg_response_time = sum(l.get('response_time_ms', 0) for l in logs) / max(total_calls, 1)
        
        # Get current limits
        limits = get_user_cost_limits(user_id)
        
        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "cached_calls": cached_calls,
            "total_tokens": total_tokens,
            "avg_response_time_ms": round(avg_response_time, 2),
            "daily_calls_used": limits.get('daily_ai_calls_used', 0),
            "daily_calls_limit": limits.get('daily_ai_calls_limit', DEFAULT_DAILY_AI_CALLS),
            "monthly_calls_used": limits.get('monthly_ai_calls_used', 0),
            "monthly_calls_limit": limits.get('monthly_ai_calls_limit', DEFAULT_MONTHLY_AI_CALLS),
            "daily_tokens_used": limits.get('daily_tokens_used', 0),
            "daily_tokens_limit": limits.get('daily_tokens_limit', DEFAULT_DAILY_TOKENS),
            "is_blocked": limits.get('is_blocked', False)
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage stats: {e}", exc_info=True)
        return {
            "total_calls": 0,
            "successful_calls": 0,
            "cached_calls": 0,
            "total_tokens": 0,
            "avg_response_time_ms": 0,
            "daily_calls_used": 0,
            "daily_calls_limit": DEFAULT_DAILY_AI_CALLS,
            "monthly_calls_used": 0,
            "monthly_calls_limit": DEFAULT_MONTHLY_AI_CALLS,
            "daily_tokens_used": 0,
            "daily_tokens_limit": DEFAULT_DAILY_TOKENS,
            "is_blocked": False
        }



