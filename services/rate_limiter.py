"""
Rate limiting service.
Prevents abuse by limiting API calls per user/IP.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import logging

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Rate limit configurations
RATE_LIMITS = {
    "webhook": {"max_requests": 100, "window_minutes": 60},  # 100 requests per hour
    "api": {"max_requests": 200, "window_minutes": 60},  # 200 requests per hour
    "messages": {"max_requests": 50, "window_minutes": 60},  # 50 messages per hour
    "insights": {"max_requests": 20, "window_minutes": 60},  # 20 insights per hour
}

# Abuse thresholds
ABUSE_THRESHOLDS = {
    "spam": {"max_messages": 10, "window_minutes": 5},  # 10 messages in 5 minutes
    "excessive_calls": {"max_calls": 20, "window_minutes": 1},  # 20 calls in 1 minute
}


def check_rate_limit(
    user_id: Optional[str],
    endpoint: str,
    ip_address: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Check if a request is within rate limits.
    
    Args:
        user_id: User ID (optional)
        endpoint: API endpoint name
        ip_address: IP address (optional)
        
    Returns:
        Tuple of (allowed: bool, reason: Optional[str], retry_after_seconds: Optional[int])
    """
    client = get_supabase_client()
    
    # Get rate limit config for endpoint
    limit_config = RATE_LIMITS.get(endpoint, RATE_LIMITS["api"])
    max_requests = limit_config["max_requests"]
    window_minutes = limit_config["window_minutes"]
    
    window_start = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    
    try:
        # Check user-based rate limit
        if user_id:
            user_logs = client.table("rate_limit_logs")\
                .select("*")\
                .eq("user_id", user_id)\
                .eq("endpoint", endpoint)\
                .gte("window_start", window_start.isoformat())\
                .execute()
            
            if user_logs.data:
                total_requests = sum(log.get('request_count', 1) for log in user_logs.data)
                if total_requests >= max_requests:
                    # Calculate retry after
                    oldest_log = min(user_logs.data, key=lambda x: x.get('window_start', ''))
                    oldest_time = datetime.fromisoformat(oldest_log['window_start'].replace('Z', '+00:00'))
                    retry_after = int((oldest_time + timedelta(minutes=window_minutes) - datetime.now(timezone.utc)).total_seconds())
                    return False, f"Rate limit exceeded: {max_requests} requests per {window_minutes} minutes", max(0, retry_after)
        
        # Check IP-based rate limit
        if ip_address:
            ip_logs = client.table("rate_limit_logs")\
                .select("*")\
                .eq("ip_address", ip_address)\
                .eq("endpoint", endpoint)\
                .gte("window_start", window_start.isoformat())\
                .execute()
            
            if ip_logs.data:
                total_requests = sum(log.get('request_count', 1) for log in ip_logs.data)
                if total_requests >= max_requests:
                    oldest_log = min(ip_logs.data, key=lambda x: x.get('window_start', ''))
                    oldest_time = datetime.fromisoformat(oldest_log['window_start'].replace('Z', '+00:00'))
                    retry_after = int((oldest_time + timedelta(minutes=window_minutes) - datetime.now(timezone.utc)).total_seconds())
                    return False, f"Rate limit exceeded for IP: {max_requests} requests per {window_minutes} minutes", max(0, retry_after)
        
        return True, None, None
        
    except Exception as e:
        logger.error(f"Error checking rate limit: {e}", exc_info=True)
        # Fail open - allow the request if rate limit check fails
        return True, None, None


def record_rate_limit_request(
    user_id: Optional[str],
    endpoint: str,
    ip_address: Optional[str] = None
) -> None:
    """
    Record a rate limit request.
    
    Args:
        user_id: User ID (optional)
        endpoint: API endpoint name
        ip_address: IP address (optional)
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc)
    
    try:
        limit_config = RATE_LIMITS.get(endpoint, RATE_LIMITS["api"])
        window_minutes = limit_config["window_minutes"]
        window_end = now + timedelta(minutes=window_minutes)
        
        # Try to update existing log in current window
        if user_id:
            existing = client.table("rate_limit_logs")\
                .select("*")\
                .eq("user_id", user_id)\
                .eq("endpoint", endpoint)\
                .gte("window_start", (now - timedelta(minutes=window_minutes)).isoformat())\
                .limit(1)\
                .execute()
            
            if existing.data and len(existing.data) > 0:
                # Update existing log
                log_id = existing.data[0]['id']
                client.table("rate_limit_logs")\
                    .update({
                        "request_count": existing.data[0].get('request_count', 0) + 1,
                        "window_end": window_end.isoformat()
                    })\
                    .eq("id", log_id)\
                    .execute()
                return
        
        # Create new log entry
        client.table("rate_limit_logs")\
            .insert({
                "user_id": user_id,
                "endpoint": endpoint,
                "ip_address": ip_address,
                "request_count": 1,
                "window_start": now.isoformat(),
                "window_end": window_end.isoformat()
            })\
            .execute()
            
    except Exception as e:
        logger.error(f"Failed to record rate limit request: {e}", exc_info=True)
        # Don't fail the request if logging fails


def check_abuse_patterns(user_id: str, message_text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check for abuse patterns in user messages.
    
    Args:
        user_id: User ID
        message_text: Message text to check
        
    Returns:
        Tuple of (is_abuse: bool, abuse_type: Optional[str], severity: Optional[str])
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc)
    
    try:
        # Check for spam (too many messages in short time)
        spam_config = ABUSE_THRESHOLDS["spam"]
        spam_window = now - timedelta(minutes=spam_config["window_minutes"])
        
        recent_messages = client.table("conversation_memory")\
            .select("id")\
            .eq("user_id", user_id)\
            .eq("direction", "incoming")\
            .gte("created_at", spam_window.isoformat())\
            .execute()
        
        message_count = len(recent_messages.data) if recent_messages.data else 0
        
        if message_count >= spam_config["max_messages"]:
            # Log abuse
            log_abuse_detection(
                user_id=user_id,
                abuse_type="spam",
                severity="medium",
                details=f"{message_count} messages in {spam_config['window_minutes']} minutes",
                action_taken="rate_limited"
            )
            return True, "spam", "medium"
        
        # Check for excessive AI calls
        excessive_config = ABUSE_THRESHOLDS["excessive_calls"]
        excessive_window = now - timedelta(minutes=excessive_config["window_minutes"])
        
        recent_calls = client.table("ai_call_logs")\
            .select("id")\
            .eq("user_id", user_id)\
            .gte("created_at", excessive_window.isoformat())\
            .execute()
        
        call_count = len(recent_calls.data) if recent_calls.data else 0
        
        if call_count >= excessive_config["max_calls"]:
            log_abuse_detection(
                user_id=user_id,
                abuse_type="excessive_calls",
                severity="high",
                details=f"{call_count} AI calls in {excessive_config['window_minutes']} minute(s)",
                action_taken="rate_limited"
            )
            return True, "excessive_calls", "high"
        
        # Check for suspicious patterns (very short messages, repeated text)
        if len(message_text) < 3:
            # Very short messages might be spam
            return False, None, None  # Don't block, but could log
        
        if len(set(message_text.split())) < 2 and len(message_text.split()) > 5:
            # Repetitive text
            log_abuse_detection(
                user_id=user_id,
                abuse_type="suspicious_pattern",
                severity="low",
                details="Repetitive message pattern detected",
                action_taken="warned"
            )
            return False, None, None  # Don't block, just log
        
        return False, None, None
        
    except Exception as e:
        logger.error(f"Error checking abuse patterns: {e}", exc_info=True)
        return False, None, None


def log_abuse_detection(
    user_id: str,
    abuse_type: str,
    severity: str,
    details: str,
    action_taken: str = "none",
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an abuse detection event.
    
    Args:
        user_id: User ID
        abuse_type: Type of abuse
        severity: Severity level
        details: Details about the abuse
        action_taken: Action taken
        metadata: Additional metadata
    """
    client = get_supabase_client()
    
    try:
        client.table("abuse_detection_logs")\
            .insert({
                "user_id": user_id,
                "abuse_type": abuse_type,
                "severity": severity,
                "details": details,
                "action_taken": action_taken,
                "metadata": metadata or {}
            })\
            .execute()
        
        logger.warning(f"Abuse detected for user {user_id}: {abuse_type} ({severity}) - {details}")
        
    except Exception as e:
        logger.error(f"Failed to log abuse detection: {e}", exc_info=True)





