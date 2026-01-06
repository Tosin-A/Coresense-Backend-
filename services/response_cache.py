"""
Response caching service.
Caches AI responses for similar inputs to reduce costs and improve response time.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import logging
import hashlib
import json

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_HOURS = 24  # Cache responses for 24 hours
CACHE_SIMILARITY_THRESHOLD = 0.9  # Minimum similarity to use cached response (not used in simple hash-based approach)


def generate_cache_key(user_id: str, prompt_text: str, max_tokens: int = 150) -> str:
    """
    Generate a cache key for a prompt.
    
    Args:
        user_id: User ID
        prompt_text: Prompt text
        max_tokens: Maximum tokens (affects response)
        
    Returns:
        Cache key string
    """
    # Create a hash of the prompt + user + max_tokens
    cache_string = f"{user_id}:{prompt_text}:{max_tokens}"
    return hashlib.sha256(cache_string.encode()).hexdigest()


def get_cached_response(user_id: str, cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Get a cached response if available and not expired.
    
    Args:
        user_id: User ID
        cache_key: Cache key
        
    Returns:
        Cached response dict or None
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc)
    
    try:
        response = client.table("ai_response_cache")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("cache_key", cache_key)\
            .or_(f"expires_at.is.null,expires_at.gt.{now.isoformat()}")\
            .limit(1)\
            .execute()
        
        if response.data and len(response.data) > 0:
            cache_entry = response.data[0]
            
            # Update hit count and last accessed
            client.table("ai_response_cache")\
                .update({
                    "hit_count": cache_entry.get('hit_count', 0) + 1,
                    "last_accessed_at": now.isoformat()
                })\
                .eq("id", cache_entry['id'])\
                .execute()
            
            logger.info(f"Cache hit for user {user_id}: {cache_key[:16]}...")
            return {
                "response_text": cache_entry['response_text'],
                "tokens_generated": cache_entry.get('tokens_generated'),
                "cached": True,
                "hit_count": cache_entry.get('hit_count', 0) + 1
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting cached response: {e}", exc_info=True)
        return None


def cache_response(
    user_id: str,
    cache_key: str,
    prompt_text: str,
    response_text: str,
    tokens_generated: int
) -> None:
    """
    Cache an AI response.
    
    Args:
        user_id: User ID
        cache_key: Cache key
        prompt_text: Original prompt (for reference)
        response_text: Generated response
        tokens_generated: Number of tokens generated
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=CACHE_TTL_HOURS)
    
    # Create prompt hash for reference
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
    
    try:
        # Use upsert to handle duplicates
        client.table("ai_response_cache")\
            .upsert({
                "user_id": user_id,
                "cache_key": cache_key,
                "prompt_hash": prompt_hash,
                "response_text": response_text,
                "tokens_generated": tokens_generated,
                "hit_count": 0,
                "last_accessed_at": now.isoformat(),
                "expires_at": expires_at.isoformat()
            }, on_conflict="user_id,cache_key")\
            .execute()
        
        logger.info(f"Cached response for user {user_id}: {cache_key[:16]}...")
        
    except Exception as e:
        logger.error(f"Failed to cache response: {e}", exc_info=True)
        # Don't fail the request if caching fails


def cleanup_expired_cache(user_id: Optional[str] = None) -> int:
    """
    Clean up expired cache entries.
    
    Args:
        user_id: Optional user ID to clean for specific user
        
    Returns:
        Number of deleted entries
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        query = client.table("ai_response_cache")\
            .delete()\
            .not_.is_("expires_at", "null")\
            .lt("expires_at", now)
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.execute()
        
        deleted_count = 1 if response.data else 0  # Placeholder
        logger.info(f"Cleaned up expired cache entries for user {user_id or 'all'}")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired cache: {e}", exc_info=True)
        return 0



