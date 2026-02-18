"""
Rate limiting middleware for FastAPI.
Applies rate limiting to API endpoints.
"""

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from typing import Callable
import logging

from backend.services.rate_limiter import check_rate_limit, record_rate_limit_request

logger = logging.getLogger(__name__)

# Paths exempt from rate limiting
EXEMPT_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting to all requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and static files
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Extract user ID from auth token via Supabase verification
        user_id = None
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "").strip()
                if token:
                    from backend.database.supabase_client import get_supabase_client
                    user_response = get_supabase_client().auth.get_user(token)
                    if user_response and user_response.user:
                        user_id = str(user_response.user.id)
        except Exception:
            pass  # Fall back to IP-based rate limiting

        # Get client IP
        client_ip = request.client.host if request.client else None

        # Determine endpoint category
        endpoint = "api"
        if "/coach/chat" in request.url.path:
            endpoint = "messages"
        elif "/insights" in request.url.path:
            endpoint = "insights"
        elif "/webhooks/" in request.url.path:
            endpoint = "webhook"

        # Check rate limit
        allowed, reason, retry_after = check_rate_limit(
            user_id=user_id,
            endpoint=endpoint,
            ip_address=client_ip
        )

        if not allowed:
            logger.warning(f"Rate limit exceeded: user={user_id}, ip={client_ip}, endpoint={endpoint}")
            return Response(
                content='{"error": "Too many requests. Please try again later."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={
                    "Retry-After": str(retry_after) if retry_after else "60",
                    "Content-Type": "application/json"
                }
            )

        # Record the request
        record_rate_limit_request(user_id=user_id, endpoint=endpoint, ip_address=client_ip)

        # Continue with request
        return await call_next(request)
