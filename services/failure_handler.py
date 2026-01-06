"""
Failure handling service.
Provides graceful degradation and fallback mechanisms.
"""

from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Fallback responses for different failure scenarios
FALLBACK_RESPONSES = {
    "model_unavailable": "I'm having trouble processing that right now. Can you try again in a moment?",
    "rate_limit": "I'm getting a lot of messages right now. Let me catch up and I'll respond soon!",
    "cost_limit": "I've reached my daily limit. I'll be back tomorrow!",
    "error": "Something went wrong. Can you rephrase that?",
    "timeout": "That took longer than expected. Let me try a shorter response.",
    "invalid_input": "I'm not sure how to respond to that. Can you ask me something else?",
}


def get_fallback_response(failure_type: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Get a fallback response for a failure scenario.
    
    Args:
        failure_type: Type of failure
        context: Optional context for customizing response
        
    Returns:
        Fallback response text
    """
    base_response = FALLBACK_RESPONSES.get(failure_type, FALLBACK_RESPONSES["error"])
    
    # Customize based on context if needed
    if context:
        user_name = context.get('user_name')
        if user_name:
            base_response = f"Hey {user_name}, {base_response.lower()}"
    
    return base_response


def handle_ai_generation_failure(
    error: Exception,
    user_id: str,
    original_message: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Handle AI generation failures gracefully.
    
    Args:
        error: The exception that occurred
        user_id: User ID
        original_message: Original user message
        context: Optional context
        
    Returns:
        Dict with fallback response and metadata
    """
    error_type = type(error).__name__
    error_message = str(error)
    
    logger.error(f"AI generation failure for user {user_id}: {error_type} - {error_message}")
    
    # Determine failure type
    if "timeout" in error_message.lower() or "time" in error_type.lower():
        failure_type = "timeout"
    elif "limit" in error_message.lower() or "quota" in error_message.lower():
        failure_type = "cost_limit"
    elif "model" in error_message.lower() or "load" in error_message.lower():
        failure_type = "model_unavailable"
    else:
        failure_type = "error"
    
    fallback_response = get_fallback_response(failure_type, context)
    
    return {
        "success": True,  # Still return success so message is sent
        "reply_text": fallback_response,
        "fallback_used": True,
        "failure_type": failure_type,
        "original_error": error_message
    }


def should_retry_failure(failure_type: str, retry_count: int = 0) -> bool:
    """
    Determine if a failure should be retried.
    
    Args:
        failure_type: Type of failure
        retry_count: Number of times already retried
        
    Returns:
        Whether to retry
    """
    max_retries = {
        "timeout": 2,
        "error": 1,
        "model_unavailable": 0,  # Don't retry if model unavailable
        "cost_limit": 0,  # Don't retry if limit reached
        "rate_limit": 0,  # Don't retry if rate limited
    }
    
    max_retry = max_retries.get(failure_type, 1)
    return retry_count < max_retry


def validate_response_quality(response_text: str) -> Tuple[bool, Optional[str]]:
    """
    Validate AI response quality before sending.
    
    Args:
        response_text: Generated response text
        
    Returns:
        Tuple of (is_valid: bool, reason: Optional[str])
    """
    # Check for empty response
    if not response_text or len(response_text.strip()) < 1:
        return False, "Response is empty"
    
    # Check for error markers
    if response_text.startswith("[") and response_text.endswith("]"):
        return False, "Response contains error marker"
    
    # Check for excessive length (safety boundary)
    if len(response_text) > 1000:  # MAX_MESSAGE_LENGTH
        return False, f"Response too long ({len(response_text)} chars, max 1000)"
    
    # Check for repetitive content
    words = response_text.split()
    if len(words) > 10 and len(set(words)) < 3:
        return False, "Response is too repetitive"
    
    # Check for only special characters
    if len(set(response_text.strip())) < 3:
        return False, "Response contains too few unique characters"
    
    return True, None

