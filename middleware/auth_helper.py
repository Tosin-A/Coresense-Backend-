"""
Authentication Helper Functions
Shared authentication utilities for all routers
"""

from fastapi import Header
import logging

from backend.database.supabase_client import get_supabase_client
from backend.utils.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


async def get_current_user_id(authorization: str = Header(...)) -> str:
    """
    Extract and validate user ID from JWT token.
    
    Args:
        authorization: Authorization header containing Bearer token
        
    Returns:
        str: Validated user ID
        
    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        if not authorization.startswith("Bearer "):
            raise AuthenticationError("Invalid authorization header format")
        
        token = authorization.replace("Bearer ", "").strip()
        
        if not token:
            raise AuthenticationError("Missing authentication token")
        
        # Verify token with Supabase
        try:
            user_response = get_supabase_client().auth.get_user(token)
        except Exception as e:
            logger.error(f"Supabase auth error: {str(e)}", exc_info=True)
            raise AuthenticationError("Failed to verify authentication token")
        
        if not user_response or not user_response.user:
            raise AuthenticationError("Invalid or expired token")
        
        return user_response.user.id
        
    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected auth error: {str(e)}", exc_info=True)
        raise AuthenticationError("Authentication failed")


# Alias for backwards compatibility with existing routers
verify_auth_token = get_current_user_id