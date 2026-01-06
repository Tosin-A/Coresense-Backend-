"""
Backend utilities module.
Provides shared utilities for Supabase responses, error handling, and common operations.
"""

from backend.utils.supabase_utils import (
    handle_supabase_response,
    handle_supabase_error,
    extract_supabase_data,
    validate_supabase_response
)
from backend.utils.exceptions import (
    CoreSenseException,
    DatabaseError,
    AuthenticationError,
    ValidationError,
    NotFoundError,
    RateLimitError
)

__all__ = [
    "handle_supabase_response",
    "handle_supabase_error",
    "extract_supabase_data",
    "validate_supabase_response",
    "CoreSenseException",
    "DatabaseError",
    "AuthenticationError",
    "ValidationError",
    "NotFoundError",
    "RateLimitError",
]

