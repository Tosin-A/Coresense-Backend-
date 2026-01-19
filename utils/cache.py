"""
Simple in-memory cache utility for caching expensive computations.

Features:
- TTL-based expiration
- Thread-safe for FastAPI concurrent requests
- Simple key-value interface
"""

import time
import threading
from typing import Any, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a cached item with expiration."""
    value: Any
    expires_at: float  # Unix timestamp when this entry expires


class MemoryCache:
    """
    Thread-safe in-memory cache with TTL support.
    """
    
    def __init__(self, default_ttl_seconds: int = 3600):
        self._data: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._data[key]
                return None
            return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        with self._lock:
            self._data[key] = CacheEntry(value=value, expires_at=time.time() + ttl)
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# Global cache instance
_cache_instance: Optional[MemoryCache] = None


def get_cache() -> MemoryCache:
    """Get the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MemoryCache(default_ttl_seconds=1800)  # 30 min TTL
    return _cache_instance


def wellness_score_key(user_id: str, date_str: str = None) -> str:
    """Generate cache key for wellness score."""
    from datetime import date
    d = date_str or date.today().isoformat()
    return f"wellness_score:{user_id}:{d}"


def insights_key(user_id: str, period: str = "weekly") -> str:
    """Generate cache key for generated insights."""
    return f"insights:{user_id}:{period}"

