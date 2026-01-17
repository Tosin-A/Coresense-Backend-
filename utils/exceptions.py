"""
Custom exception classes for CoreSense backend.
Provides standardized exception types that map to appropriate HTTP status codes.
"""

from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class CoreSenseException(HTTPException):
    """Base exception class for CoreSense backend errors."""
    
    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str = "An error occurred",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class DatabaseError(CoreSenseException):
    """Exception for database operation failures."""
    
    def __init__(
        self,
        detail: str = "Database operation failed",
        original_error: Optional[Exception] = None
    ):
        error_detail = detail
        if original_error:
            error_detail = f"{detail}: {str(original_error)}"
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )


class AuthenticationError(CoreSenseException):
    """Exception for authentication failures."""
    
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail
        )


class AuthorizationError(CoreSenseException):
    """Exception for authorization failures (permission denied)."""
    
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class ValidationError(CoreSenseException):
    """Exception for validation failures."""
    
    def __init__(self, detail: str = "Validation failed", field: Optional[str] = None):
        if field:
            detail = f"Validation failed for field '{field}': {detail}"
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class NotFoundError(CoreSenseException):
    """Exception for resource not found errors."""
    
    def __init__(self, resource: str = "Resource", resource_id: Optional[str] = None):
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} with ID '{resource_id}' not found"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class ConflictError(CoreSenseException):
    """Exception for resource conflicts (e.g., duplicate entries)."""
    
    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )


class RateLimitError(CoreSenseException):
    """Exception for rate limit violations."""
    
    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        retry_after: Optional[int] = None
    ):
        headers = None
        if retry_after:
            headers = {"Retry-After": str(retry_after)}
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers=headers
        )


class ServiceUnavailableError(CoreSenseException):
    """Exception for service unavailability."""
    
    def __init__(self, detail: str = "Service temporarily unavailable"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )


class BadGatewayError(CoreSenseException):
    """Exception for bad gateway errors (e.g., external service failures)."""
    
    def __init__(self, detail: str = "External service error"):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail
        )



