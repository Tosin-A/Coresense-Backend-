"""
Supabase response handling utilities.
Provides standardized functions for handling Supabase API responses and errors.
"""

from typing import Any, Dict, List, Optional, TypeVar
from supabase import Client
from supabase.lib.client_options import ClientOptions
import logging

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

T = TypeVar('T')


def handle_supabase_response(
    response: Any,
    error_message: str = "Database operation failed",
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
) -> Any:
    """
    Handle Supabase response and extract data or raise HTTPException.
    
    Args:
        response: Supabase response object
        error_message: Custom error message if operation fails
        status_code: HTTP status code for error (default: 500)
        
    Returns:
        Response data if successful
        
    Raises:
        HTTPException: If response indicates an error
    """
    try:
        if hasattr(response, 'data'):
            return response.data
        elif hasattr(response, 'error'):
            error = response.error
            logger.error(f"Supabase error: {error}")
            raise HTTPException(
                status_code=status_code,
                detail=error_message if not error else f"{error_message}: {str(error)}"
            )
        else:
            # Response might be the data directly
            return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error handling Supabase response: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status_code,
            detail=f"{error_message}: {str(e)}"
        )


def handle_supabase_error(
    error: Exception,
    error_message: str = "Database operation failed",
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
) -> None:
    """
    Handle Supabase errors and raise appropriate HTTPException.
    
    Args:
        error: Exception raised by Supabase operation
        error_message: Custom error message
        status_code: HTTP status code for error
        
    Raises:
        HTTPException: Always raises with appropriate error details
    """
    error_str = str(error)
    logger.error(f"Supabase error: {error_str}", exc_info=True)
    
    # Check for common Supabase error patterns
    if "duplicate key" in error_str.lower() or "unique constraint" in error_str.lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource already exists"
        )
    elif "foreign key" in error_str.lower() or "not found" in error_str.lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced resource not found"
        )
    elif "permission denied" in error_str.lower() or "unauthorized" in error_str.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    else:
        raise HTTPException(
            status_code=status_code,
            detail=f"{error_message}: {error_str}"
        )


def extract_supabase_data(
    response: Any,
    default: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Extract data from Supabase response, returning default if empty.
    
    Args:
        response: Supabase response object
        default: Default value if response is empty (default: empty list)
        
    Returns:
        List of dictionaries from response data
    """
    if default is None:
        default = []
    
    try:
        if hasattr(response, 'data'):
            return response.data if response.data else default
        elif isinstance(response, list):
            return response if response else default
        else:
            return default
    except Exception as e:
        logger.warning(f"Error extracting Supabase data: {str(e)}")
        return default


def validate_supabase_response(
    response: Any,
    required_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Validate Supabase response contains expected data structure.
    
    Args:
        response: Supabase response object
        required_fields: List of required field names
        
    Returns:
        Validated data dictionary
        
    Raises:
        HTTPException: If validation fails
    """
    data = handle_supabase_response(response, "Invalid response from database")
    
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid response format from database"
        )
    
    if required_fields:
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Missing required fields in response: {', '.join(missing_fields)}"
            )
    
    return data


def get_first_item_or_none(
    response: Any,
    error_message: str = "Failed to retrieve data"
) -> Optional[Dict[str, Any]]:
    """
    Get first item from Supabase response or None if empty.
    
    Args:
        response: Supabase response object
        error_message: Error message if operation fails
        
    Returns:
        First item as dictionary or None
    """
    data = extract_supabase_data(response)
    if data and len(data) > 0:
        return data[0]
    return None

