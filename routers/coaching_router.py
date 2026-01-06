"""
Unified Coaching Router - Consolidated endpoints for all coaching functionality
Replaces openai_coach.py and ai_coach.py with unified, consistent endpoints
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from backend.services.coaching_service import (
    unified_coaching_service,
    CoachingResponseType,
    CoachingResponse,
    CoachingContext,
    get_model_info
)
from backend.middleware.auth_helper import get_current_user_id
from backend.utils.exceptions import (
    DatabaseError,
    ValidationError,
    NotFoundError,
    AuthorizationError,
    CoreSenseException
)
from fastapi import status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/coach", tags=["unified-coaching"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CoachingChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    response_type: Optional[CoachingResponseType] = CoachingResponseType.COACHING


class CoachingChatResponse(BaseModel):
    messages: List[str]
    personality_score: float
    context_used: List[str]
    variation_applied: bool
    response_type: CoachingResponseType
    thread_id: Optional[str] = None
    function_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage_stats: Optional[Dict[str, Any]] = None


class CoachingContextRequest(BaseModel):
    user_state: Dict[str, Any]
    conversation_context: List[Dict[str, Any]] = Field(default_factory=list)
    health_context: Optional[Dict[str, Any]] = None
    time_context: Dict[str, Any]


class CoachingInsightsResponse(BaseModel):
    user_id: str
    context: Dict[str, Any]
    insights: Dict[str, Any]
    recommendations: List[str]
    usage_stats: Dict[str, Any]
    patterns: Dict[str, Any]


class CoachingStatusResponse(BaseModel):
    status: str
    status_color: str
    user_id: str
    relationship_stage: str
    attachment_level: str
    relationship_score: float
    coach_available: bool
    last_interaction: Optional[str] = None


class MemoryUpdateRequest(BaseModel):
    memory_type: str
    title: str
    content: str
    importance: Optional[float] = 0.5


class MemoryUpdateResponse(BaseModel):
    success: bool
    message: str


class SignaturePhrasesRequest(BaseModel):
    category: str


class SignaturePhrasesResponse(BaseModel):
    category: str
    phrases: List[str]
    count: int


class PatternAnalysisRequest(BaseModel):
    message: str


class PatternAnalysisResponse(BaseModel):
    message: str
    analysis: Dict[str, Any]
    success: bool


class UsageStatsResponse(BaseModel):
    allowed: bool
    messages_used: int
    messages_limit: int
    is_pro: bool
    messages_remaining: int
    usage_percentage: float


@router.post("/custom-gpt/chat", response_model=CoachingChatResponse)
async def chat_with_coach_custom_gpt(
    request: CoachingChatRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Custom GPT chat endpoint - mirrors the main chat endpoint"""
    try:
        logger.info(f"🚀 CUSTOM GPT CHAT - User: {current_user_id}, Message: '{request.message[:50]}{'...' if len(request.message) > 50 else ''}'")
        
        response = await unified_coaching_service.chat(
            user_id=current_user_id,
            message=request.message,
            response_type=request.response_type,
            context=request.context
        )
        
        logger.info(f"✅ CUSTOM GPT CHAT COMPLETE - Messages: {len(response.messages)}")
        
        return CoachingChatResponse(
            messages=response.messages,
            personality_score=response.personality_score,
            context_used=response.context_used,
            variation_applied=response.variation_applied,
            response_type=response.response_type,
            thread_id=response.thread_id,
            function_calls=response.function_calls,
            usage_stats=response.usage_stats
        )
        
    except (CoreSenseException, DatabaseError, ValidationError, NotFoundError, AuthorizationError):
        raise
    except Exception as e:
        logger.error(f"❌ ERROR in custom gpt chat: {e}", exc_info=True)
        raise DatabaseError("Failed to generate coach response", original_error=e)


@router.get("/history/{user_id}")
async def get_chat_history(
    user_id: str,
    limit: int = 50,
    offset: int = 0
):
    """Get chat history for a user from OpenAI thread"""
    try:
        logger.info(f"📜 Getting chat history for user: {user_id}, limit: {limit}, offset: {offset}")
        
        from backend.services.thread_management import thread_management
        from backend.database.supabase_client import get_supabase_client
        
        # Get user's thread ID
        supabase = get_supabase_client()
        thread_response = supabase.table("assistant_threads").select(
            "openai_thread_id, created_at"
        ).eq("user_id", user_id).eq("status", "active").execute()
        
        if not thread_response.data:
            return {"messages": [], "has_more": False}
        
        thread_id = thread_response.data[0]["openai_thread_id"]
        
        # Get messages from OpenAI
        if thread_management.client:
            messages = thread_management.client.beta.threads.messages.list(
                thread_id=thread_id,
                limit=limit
            )
            
            formatted_messages = []
            for msg in messages.data:
                content = ""
                if msg.content:
                    for c in msg.content:
                        if c.type == "text":
                            content = c.text.value
                            break
                
                formatted_messages.append({
                    "id": msg.id,
                    "text": content,
                    "direction": "outbound" if msg.role == "user" else "inbound",
                    "timestamp": msg.created_at,
                    "read": True
                })
            
            return {
                "messages": formatted_messages,
                "has_more": len(messages.data) >= limit
            }
        else:
            # Return empty if OpenAI client not available
            return {"messages": [], "has_more": False}
        
    except Exception as e:
        logger.error(f"❌ Error getting chat history: {e}", exc_info=True)
        return {
            "messages": [],
            "has_more": False,
            "error": str(e)
        }


# ============================================================================
# MAIN COACHING ENDPOINTS
# ============================================================================

@router.post("/chat", response_model=CoachingChatResponse)
async def chat_with_coach(
    request: CoachingChatRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Unified chat endpoint - handles all coaching conversation types"""
    try:
        logger.info(f"🚀 UNIFIED CHAT - User: {current_user_id}, Type: {request.response_type}, Message: '{request.message[:50]}{'...' if len(request.message) > 50 else ''}'")
        
        # Use unified coaching service
        response = await unified_coaching_service.chat(
            user_id=current_user_id,
            message=request.message,
            response_type=request.response_type,
            context=request.context
        )
        
        logger.info(f"✅ UNIFIED CHAT COMPLETE - Messages: {len(response.messages)}, Type: {response.response_type}")
        
        return CoachingChatResponse(
            messages=response.messages,
            personality_score=response.personality_score,
            context_used=response.context_used,
            variation_applied=response.variation_applied,
            response_type=response.response_type,
            thread_id=response.thread_id,
            function_calls=response.function_calls,
            usage_stats=response.usage_stats
        )
        
    except (CoreSenseException, DatabaseError, ValidationError, NotFoundError, AuthorizationError):
        raise
    except Exception as e:
        logger.error(f"❌ ERROR in unified chat: {e}", exc_info=True)
        raise DatabaseError("Failed to generate coach response", original_error=e)


@router.get("/context/{user_id}", response_model=Dict[str, Any])
async def get_user_coaching_context(user_id: str):
    """Get comprehensive user coaching context"""
    try:
        context = await unified_coaching_service.get_user_context(user_id)
        
        return {
            "user_id": user_id,
            "context": {
                "user_name": context.user_name,
                "current_streak": context.current_streak,
                "longest_streak": context.longest_streak,
                "active_commitments": context.active_commitments,
                "attachment_level": context.attachment_level,
                "relationship_stage": context.relationship_stage,
                "communication_preferences": context.communication_preferences,
                "health_context": context.health_context,
                "time_context": context.time_context
            },
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Error getting user coaching context: {e}")
        return {
            "user_id": user_id,
            "error": str(e),
            "success": False
        }


@router.get("/insights/{user_id}", response_model=CoachingInsightsResponse)
async def get_coaching_insights(user_id: str):
    """Get comprehensive coaching insights and statistics"""
    try:
        insights = await unified_coaching_service.get_coaching_insights(user_id)
        
        return CoachingInsightsResponse(
            user_id=insights["user_id"],
            context=insights["context"],
            insights=insights["insights"],
            recommendations=insights["recommendations"],
            usage_stats=insights["usage_stats"],
            patterns=insights["patterns"]
        )
        
    except Exception as e:
        logger.error(f"Error getting coaching insights: {e}")
        raise DatabaseError("Failed to get coaching insights", original_error=e)


@router.get("/status/{user_id}", response_model=CoachingStatusResponse)
async def get_coach_status(user_id: str):
    """Get coach status and relationship metrics"""
    try:
        # Get user context for status calculation
        context = await unified_coaching_service.get_user_context(user_id)
        
        # Get coach status
        status_info = unified_coaching_service.get_coach_status(user_id, context)
        
        return CoachingStatusResponse(
            status=status_info["status"],
            status_color=status_info["status_color"],
            user_id=status_info["user_id"],
            relationship_stage=status_info["relationship_stage"],
            attachment_level=status_info["attachment_level"],
            relationship_score=status_info["relationship_score"],
            coach_available=status_info["coach_available"],
            last_interaction=status_info["last_interaction"]
        )
        
    except Exception as e:
        logger.error(f"Error getting coach status: {e}")
        return CoachingStatusResponse(
            status="Unavailable",
            status_color="error",
            user_id=user_id,
            relationship_stage="unknown",
            attachment_level="unknown",
            relationship_score=0.0,
            coach_available=False
        )


@router.get("/usage/{user_id}", response_model=UsageStatsResponse)
async def get_message_usage(user_id: str):
    """Get user's message usage statistics"""
    try:
        from backend.services.message_limit_service import get_user_usage_stats
        
        stats = get_user_usage_stats(user_id)
        allowed = stats['is_pro'] or stats['messages_remaining'] > 0
        
        return UsageStatsResponse(
            allowed=allowed,
            messages_used=stats['messages_used'],
            messages_limit=stats['messages_limit'],
            is_pro=stats['is_pro'],
            messages_remaining=stats['messages_remaining'],
            usage_percentage=stats['usage_percentage']
        )
    except Exception as e:
        logger.error(f"Error getting usage stats for user {user_id}: {e}")
        raise DatabaseError("Failed to get usage stats", original_error=e)


# ============================================================================
# MEMORY AND CONTEXT MANAGEMENT
# ============================================================================

@router.post("/memory", response_model=MemoryUpdateResponse)
async def update_user_memory(
    request: MemoryUpdateRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Update user coaching memory"""
    try:
        success = await unified_coaching_service.update_user_memory(
            user_id=current_user_id,
            memory_type=request.memory_type,
            title=request.title,
            content=request.content,
            importance=request.importance
        )
        
        return MemoryUpdateResponse(
            success=success,
            message="Memory updated successfully" if success else "Failed to update memory"
        )
        
    except Exception as e:
        logger.error(f"Error updating user memory: {e}")
        raise DatabaseError("Failed to update memory", original_error=e)


@router.get("/signature-phrases/{category}", response_model=SignaturePhrasesResponse)
async def get_coach_signature_phrases(category: str):
    """Get coach signature phrases by category"""
    try:
        phrases = unified_coaching_service.get_signature_phrases(category)
        
        return SignaturePhrasesResponse(
            category=category,
            phrases=phrases,
            count=len(phrases)
        )
        
    except Exception as e:
        logger.error(f"Error getting signature phrases: {e}")
        return SignaturePhrasesResponse(
            category=category,
            phrases=["What's the plan bro?"],
            count=1
        )


@router.post("/analyze-pattern", response_model=PatternAnalysisResponse)
async def analyze_user_message_pattern(request: PatternAnalysisRequest):
    """Analyze user message for coaching approach"""
    try:
        analysis = unified_coaching_service.analyze_user_pattern(request.message)
        
        return PatternAnalysisResponse(
            message=analysis["message"],
            analysis=analysis["analysis"],
            success=analysis["success"]
        )
        
    except Exception as e:
        logger.error(f"Error analyzing user pattern: {e}")
        return PatternAnalysisResponse(
            message=request.message,
            analysis={"approach": "general_check", "pressure": "balanced"},
            success=False,
            error=str(e)
        )


# ============================================================================
# BACKWARD COMPATIBILITY ENDPOINTS
# ============================================================================

@router.post("/greeting", response_model=CoachingChatResponse)
async def get_coach_greeting(
    context: CoachingContextRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Backward compatibility: Get contextual coach greeting"""
    try:
        context_data = {
            "user_state": context.user_state,
            "conversation_context": context.conversation_context,
            "health_context": context.health_context,
            "time_context": context.time_context
        }
        
        response = await unified_coaching_service.chat(
            user_id=current_user_id,
            message="Hello",
            response_type=CoachingResponseType.GREETING,
            context=context_data
        )
        
        return CoachingChatResponse(
            messages=response.messages,
            personality_score=response.personality_score,
            context_used=response.context_used,
            variation_applied=response.variation_applied,
            response_type=response.response_type,
            thread_id=response.thread_id,
            function_calls=response.function_calls,
            usage_stats=response.usage_stats
        )
        
    except Exception as e:
        logger.error(f"Error generating coach greeting: {e}")
        # Return fallback greeting
        return CoachingChatResponse(
            messages=["Hey. What's the plan today?"],
            personality_score=0.5,
            context_used=[],
            variation_applied=False,
            response_type=CoachingResponseType.GREETING
        )


@router.post("/pressure", response_model=CoachingChatResponse)
async def get_coach_pressure(
    context: CoachingContextRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Backward compatibility: Get appropriate pressure message from coach"""
    try:
        context_data = {
            "user_state": context.user_state,
            "conversation_context": context.conversation_context,
            "health_context": context.health_context,
            "time_context": context.time_context
        }
        
        response = await unified_coaching_service.chat(
            user_id=current_user_id,
            message="I need some pressure",
            response_type=CoachingResponseType.PRESSURE,
            context=context_data
        )
        
        return CoachingChatResponse(
            messages=response.messages,
            personality_score=response.personality_score,
            context_used=response.context_used,
            variation_applied=response.variation_applied,
            response_type=response.response_type,
            thread_id=response.thread_id,
            function_calls=response.function_calls,
            usage_stats=response.usage_stats
        )
        
    except Exception as e:
        logger.error(f"Error generating coach pressure: {e}")
        # Return fallback pressure message
        return CoachingChatResponse(
            messages=["Talk to me.", "What's going on?"],
            personality_score=0.6,
            context_used=[],
            variation_applied=False,
            response_type=CoachingResponseType.PRESSURE
        )


@router.get("/stats/{user_id}")
async def get_coaching_statistics(user_id: str):
    """Backward compatibility: Get coaching usage statistics and insights"""
    try:
        insights = await unified_coaching_service.get_coaching_insights(user_id)
        
        return {
            "user_id": user_id,
            "total_interactions": insights["usage_stats"].get("messages_used", 0),
            "relationship_stage": insights["context"].get("relationship_stage", "unknown"),
            "attachment_level": insights["context"].get("attachment_level", "unknown"),
            "preferred_coaching_style": insights["insights"].get("engagement_level", "unknown"),
            "response_effectiveness": insights["insights"].get("coaching_effectiveness", 0.5),
            "insights": insights["insights"],
            "recommendations": insights["recommendations"]
        }
        
    except Exception as e:
        logger.error(f"Error getting coaching statistics: {e}")
        return {
            "user_id": user_id,
            "total_interactions": 0,
            "relationship_stage": "unknown",
            "attachment_level": "unknown",
            "preferred_coaching_style": "unknown",
            "response_effectiveness": 0.0,
            "error": str(e)
        }


# ============================================================================
# HEALTH CHECK AND STATUS
# ============================================================================

@router.get("/status")
async def get_coaching_service_status():
    """Get coaching service status"""
    try:
        return {
            "status": "healthy",
            "service": "unified-coaching",
            "version": "2.0.0",
            "features": [
                "unified_chat",
                "context_management", 
                "memory_storage",
                "pattern_analysis",
                "message_limits",
                "signature_phrases"
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting coaching service status: {e}")
        return {
            "status": "error",
            "service": "unified-coaching",
            "error": str(e)
        }


@router.get("/health")
async def coaching_health_check():
    """Health check endpoint for coaching service"""
    return {
        "status": "healthy",
        "service": "unified-coaching",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# AI COACH ENDPOINTS (MIGRATED FROM ai_coach.py)
# ============================================================================

@router.get("/model-info")
async def get_model_info_endpoint(
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get detailed model information.
    Requires authentication.
    """
    try:
        info = get_model_info()
        return info
    except Exception as e:
        logger.error(f"Error getting model info: {e}", exc_info=True)
        raise DatabaseError("Failed to get model info", original_error=e)
