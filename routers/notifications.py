"""
Waiting Messages API Router
Handles notification management and waiting message delivery
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from backend.services.notification_service import notification_service, WaitingMessage
from backend.database.supabase_client import get_supabase_client
from backend.utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class QueueMessageRequest(BaseModel):
    message_text: str
    message_type: str = "coach_message"
    priority: str = "normal"
    scheduled_for: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None


class CheckinRequest(BaseModel):
    message: str
    priority: str = "normal"


class PatternAlertRequest(BaseModel):
    pattern_type: str
    message: str


class AccountabilityNudgeRequest(BaseModel):
    nudge_type: str  # deadline, missed_streak, pattern_broken
    message: str


@router.post("/queue-message")
async def queue_waiting_message(
    request: QueueMessageRequest,
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Queue a message for later delivery"""
    try:
        message = WaitingMessage(
            user_id=user_id,
            message_text=request.message_text,
            message_type=request.message_type,
            priority=request.priority,
            scheduled_for=request.scheduled_for,
            context=request.context
        )
        
        success = await notification_service.queue_waiting_message(message)
        
        if success:
            return {"success": True, "message": "Message queued successfully"}
        else:
            raise DatabaseError("Failed to queue message", original_error=e)
            
    except Exception as e:
        logger.error(f"Error queueing message: {e}")
        raise DatabaseError("Failed to queue message", original_error=e)


@router.get("/waiting-messages")
async def get_waiting_messages(
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Get all waiting messages for a user"""
    try:
        messages = await notification_service.get_waiting_messages(user_id)
        
        return {
            "success": True,
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Error getting waiting messages: {e}")
        raise DatabaseError("Failed to get waiting messages", original_error=e)


@router.post("/mark-delivered/{message_id}")
async def mark_message_delivered(
    message_id: str,
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Mark a waiting message as delivered"""
    try:
        success = await notification_service.mark_message_delivered(message_id)
        
        if success:
            return {"success": True, "message": "Message marked as delivered"}
        else:
            raise DatabaseError("Failed to mark message as delivered")
            
    except Exception as e:
        logger.error(f"Error marking message delivered: {e}")
        raise DatabaseError("Failed to mark message as delivered", original_error=e)


@router.post("/coach-checkin")
async def send_coach_checkin(
    request: CheckinRequest,
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Send a coach check-in message"""
    try:
        success = await notification_service.send_coach_checkin(
            user_id=user_id,
            message=request.message,
            priority=request.priority
        )
        
        if success:
            return {"success": True, "message": "Check-in message sent"}
        else:
            raise DatabaseError("Failed to send check-in message")
            
    except Exception as e:
        logger.error(f"Error sending coach checkin: {e}")
        raise DatabaseError("Failed to send check-in message", original_error=e)


@router.post("/pattern-alert")
async def send_pattern_alert(
    request: PatternAlertRequest,
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Send a pattern-based alert message"""
    try:
        success = await notification_service.send_pattern_alert(
            user_id=user_id,
            pattern_type=request.pattern_type,
            message=request.message
        )
        
        if success:
            return {"success": True, "message": "Pattern alert sent"}
        else:
            raise DatabaseError("Failed to send pattern alert")
            
    except Exception as e:
        logger.error(f"Error sending pattern alert: {e}")
        raise DatabaseError("Failed to send pattern alert", original_error=e)


@router.post("/accountability-nudge")
async def send_accountability_nudge(
    request: AccountabilityNudgeRequest,
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Send an accountability nudge"""
    try:
        success = await notification_service.send_accountability_nudge(
            user_id=user_id,
            nudge_type=request.nudge_type,
            message=request.message
        )
        
        if success:
            return {"success": True, "message": "Accountability nudge sent"}
        else:
            raise DatabaseError("Failed to send accountability nudge")
            
    except Exception as e:
        logger.error(f"Error sending accountability nudge: {e}")
        raise DatabaseError("Failed to send accountability nudge", original_error=e)


@router.get("/stats")
async def get_notification_stats(
    user_id: str = Depends(lambda authorization: "user_id")  # TODO: Implement proper auth
):
    """Get notification statistics for a user"""
    try:
        stats = await notification_service.get_notification_stats(user_id)
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting notification stats: {e}")
        raise DatabaseError("Failed to get notification stats", original_error=e)


@router.post("/test-coach-message")
async def test_coach_message(
    user_id: str = "c18f7b13-6d6a-42d6-ac2e-c67cf90e1d1e"  # Test user ID
):
    """Test endpoint to send a coach message"""
    try:
        # Send a test coach message
        success = await notification_service.send_coach_checkin(
            user_id=user_id,
            message="Hey. Still on track today?",
            priority="normal"
        )
        
        if success:
            return {"success": True, "message": "Test coach message sent"}
        else:
            raise DatabaseError("Failed to send test message")
            
    except Exception as e:
        logger.error(f"Error sending test coach message: {e}")
        raise DatabaseError("Failed to send test message", original_error=e)