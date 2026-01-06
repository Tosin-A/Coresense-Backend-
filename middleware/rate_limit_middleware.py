"""
Rate limiting middleware for FastAPI.
Applies rate limiting to API endpoints.
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from typing import Callable
import logging

from services.rate_limiter import check_rate_limit, record_rate_limit_request

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting to all requests."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and static files
        if request.url.path in ["/health", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        
        # Get user ID from auth token if available
        user_id = None
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                # Extract user ID from JWT (simplified - in production, verify signature)
                from jose import jwt
                token = auth_header.replace("Bearer ", "")
                payload = jwt.decode(token, options={"verify_signature": False})
                user_id = payload.get("sub")
        except Exception:
            pass  # Continue without user ID
        
        # Get client IP
        client_ip = request.client.host if request.client else None
        
        # Determine endpoint name
        endpoint = request.url.path.split("/")[-1] or "api"
        if "/api/" in request.url.path:
            endpoint = "api"
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
                content=f'{{"error": "{reason}"}}',
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



