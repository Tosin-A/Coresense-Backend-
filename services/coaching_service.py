"""
Unified Coaching Service - Core of the Merger
Combines the best of openai_coach_service, ai_coach.py, and custom_gpt_service
Assistant-Native architecture with minimal context injection
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

from .thread_management import thread_management
from .context_service import context_service
from .message_limit_service import (
    check_message_limit,
    increment_message_count,
    get_user_usage_stats
)
from .message_storage_service import message_storage
from .model_router import model_router
from utils.exceptions import CoreSenseException
from fastapi import status

logger = logging.getLogger(__name__)


def get_model_info():
    """Get information about the AI coach model."""
    return {
        "available": True,
        "model_name": "Custom GPT Coach",
        "version": "1.0.0",
        "features": ["personalized_coaching", "memory_integration", "pattern_recognition"],
        "status": "active"
    }


def is_model_available():
    """Check if the AI coach model is available."""
    return True


class CoachingResponseType(str, Enum):
    """Response types for coaching messages"""
    COACHING = "coaching"
    GREETING = "greeting"
    PRESSURE = "pressure"
    ADVICE = "advice"
    STATS = "stats"
    INSIGHTS = "insights"
    CHECK_IN = "check_in"
    SUPPORT = "support"
    CELEBRATION = "celebration"


@dataclass
class CoachingContext:
    """Unified coaching context"""
    user_id: str
    user_name: str
    current_streak: int
    longest_streak: int
    active_commitments: List[str]
    attachment_level: str = "initial"
    relationship_stage: str = "initial"
    communication_preferences: Dict[str, Any] = None
    health_context: Dict[str, Any] = None
    time_context: Dict[str, Any] = None


@dataclass
class CoachingResponse:
    """Unified coaching response"""
    messages: List[str]
    personality_score: float
    context_used: List[str]
    variation_applied: bool
    response_type: CoachingResponseType
    thread_id: Optional[str] = None
    run_id: Optional[str] = None  # Current run ID for delta tracking
    function_calls: List[Dict[str, Any]] = None
    usage_stats: Optional[Dict[str, Any]] = None
    # Reconciliation data - optional to handle partial failures
    saved_ids: Optional[Dict[str, Optional[str]]] = None  # {"user_message": "db-uuid" or None, "assistant_temp_ids": [...]}
    client_temp_id: Optional[str] = None  # Echo back the client's temp ID


class UnifiedCoachingService:
    """
    Unified Coaching Service - Single source of truth for all coaching logic
    
    Features:
    - Assistant-Native architecture (leverages thread_management)
    - Minimal context injection (leverages context_service)
    - Message limit integration
    - Unified error handling
    - Consistent response formats
    """
    
    def __init__(self):
        self.thread_manager = thread_management
        self.context_mgr = context_service
        
        # Function definitions for the assistant
        self.functions = [
            {
                "type": "function",
                "function": {
                    "name": "get_user_memory",
                    "description": "Retrieve stored user coaching memories and preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "memory_types": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "default": ["preferences", "goals", "patterns", "commitments"]
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "store_user_memory",
                    "description": "Store important coaching insights and user preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "memory_type": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "importance": {"type": "number", "default": 0.5}
                        },
                        "required": ["user_id", "memory_type", "title", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_conversation_pattern",
                    "description": "Analyze conversation for coaching insights",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "recent_messages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Recent conversation messages"
                            },
                            "analysis_type": {"type": "string"}
                        },
                        "required": ["user_id", "recent_messages"]
                    }
                }
            }
        ]
    
    async def chat(
        self, 
        user_id: str, 
        message: str, 
        response_type: CoachingResponseType = CoachingResponseType.COACHING,
        context: Optional[Dict[str, Any]] = None,
        client_temp_id: Optional[str] = None
    ) -> CoachingResponse:
        """
        Main chat method - unified entry point for all coaching conversations
        """
        try:
            # Check message limits FIRST
            allowed, reason, limits = check_message_limit(user_id)
            
            if not allowed:
                usage_stats = get_user_usage_stats(user_id)
                raise CoreSenseException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "message_limit_reached",
                        "message": "You've reached your free message limit. Upgrade to Pro for unlimited messages.",
                        "usage": {
                            "messages_used": usage_stats['messages_used'],
                            "messages_limit": usage_stats['messages_limit'],
                            "is_pro": usage_stats['is_pro'],
                            "messages_remaining": usage_stats['messages_remaining'],
                            "usage_percentage": usage_stats['usage_percentage']
                        }
                    }
                )
            
            logger.info(f"🚀 STARTING COACHING CHAT - User: {user_id}, Type: {response_type}, Message: '{message[:50]}{'...' if len(message) > 50 else ''}'")
            
            # Get user thread
            thread_id = await self.thread_manager.get_or_create_user_thread(user_id)
            
            # Add user message to thread
            await self.thread_manager.add_message_to_thread(thread_id, message, "user")
            
            # Store user message in database
            user_chat_id = await message_storage.store_user_message(
                user_id=user_id,
                content=message,
                thread_id=thread_id,
                client_temp_id=client_temp_id
            )
            
            # Run assistant - don't pass instructions so Assistant uses its system prompt
            result = await self.thread_manager.run_assistant(
                thread_id=thread_id,
                user_id=user_id,
                response_type=response_type.value
                # No instructions - use Assistant's built-in personality
            )
            
            # Store assistant messages in database
            saved_ids: Dict[str, Optional[str]] = {}
            if user_chat_id:
                saved_ids["user_message"] = user_chat_id
            
            # Track assistant temp IDs for client reconciliation
            assistant_temp_ids: List[str] = []
            
            # Get run_id from result for delta tracking
            current_run_id = result.get("run_id")
            
            for idx, msg_content in enumerate(result["messages"]):
                # Generate assistant_temp_id for each message (like client_temp_id for user messages)
                assistant_temp_id = f"assistant_{current_run_id}_{idx}" if current_run_id else str(uuid.uuid4())
                assistant_temp_ids.append(assistant_temp_id)
                
                coach_msg_id = await message_storage.store_assistant_message(
                    user_id=user_id,
                    content=msg_content,
                    thread_id=thread_id,
                    chat_id=user_chat_id,
                    run_id=current_run_id,
                    assistant_temp_id=assistant_temp_id
                )
                saved_ids[f"coach_message_{idx}"] = coach_msg_id
            
            # Store assistant temp IDs for client reconciliation
            saved_ids["assistant_temp_ids"] = assistant_temp_ids
            
            # Filter out None values before returning
            saved_ids = {k: v for k, v in saved_ids.items() if v is not None}
            
            # Increment message count
            increment_message_count(user_id)
            
            # Get updated usage stats
            usage_stats = get_user_usage_stats(user_id)
            
            logger.info(f"✅ COACHING CHAT COMPLETE - Messages: {len(result['messages'])}, Type: {response_type}")
            
            return CoachingResponse(
                messages=result["messages"],
                personality_score=self._calculate_personality_score(response_type),
                context_used=result.get("context_used", ["assistant_memory"]),
                variation_applied=True,
                response_type=response_type,
                thread_id=thread_id,
                run_id=current_run_id,  # Include run_id for delta tracking
                function_calls=result.get("function_calls", []),
                usage_stats=usage_stats,
                saved_ids=saved_ids,
                client_temp_id=client_temp_id
            )
            
        except (CoreSenseException, Exception) as e:
            logger.error(f"❌ ERROR in coaching chat: {e}")
            raise
    
    async def get_user_context(self, user_id: str) -> CoachingContext:
        """Get comprehensive user coaching context"""
        try:
            # Get essential context
            essential_context = await self.context_mgr.get_essential_context(user_id, "minimal")
            
            # Get additional coaching-specific context
            coaching_context = await self._get_coaching_context(user_id)
            
            return CoachingContext(
                user_id=user_id,
                user_name=essential_context.user_name,
                current_streak=essential_context.current_streak,
                longest_streak=essential_context.longest_streak,
                active_commitments=essential_context.active_commitments,
                **coaching_context
            )
            
        except Exception as e:
            logger.error(f"Error getting user context: {e}")
            return CoachingContext(
                user_id=user_id,
                user_name="User",
                current_streak=0,
                longest_streak=0,
                active_commitments=[]
            )
    
    async def get_coaching_insights(self, user_id: str) -> Dict[str, Any]:
        """Get coaching insights and statistics"""
        try:
            context = await self.get_user_context(user_id)
            
            # Get usage statistics
            usage_stats = get_user_usage_stats(user_id)
            
            # Analyze patterns
            patterns = await self._analyze_coaching_patterns(user_id)
            
            return {
                "user_id": user_id,
                "context": {
                    "user_name": context.user_name,
                    "current_streak": context.current_streak,
                    "longest_streak": context.longest_streak,
                    "active_commitments": context.active_commitments,
                    "attachment_level": context.attachment_level,
                    "relationship_stage": context.relationship_stage
                },
                "insights": {
                    "engagement_level": self._calculate_engagement_level(usage_stats),
                    "streak_progress": self._calculate_streak_progress(context),
                    "commitment_adherence": self._calculate_commitment_adherence(context),
                    "coaching_effectiveness": self._calculate_effectiveness(usage_stats)
                },
                "recommendations": self._generate_recommendations(context, usage_stats, patterns),
                "usage_stats": usage_stats,
                "patterns": patterns
            }
            
        except Exception as e:
            logger.error(f"Error getting coaching insights: {e}")
            return {
                "user_id": user_id,
                "error": str(e),
                "insights": {},
                "recommendations": []
            }
    
    async def update_user_memory(self, user_id: str, memory_type: str, title: str, content: str, importance: float = 0.5) -> bool:
        """Update user coaching memory"""
        try:
            return await self.thread_manager.execute_function(
                user_id=user_id,
                function_name="store_user_memory",
                arguments={
                    "user_id": user_id,
                    "memory_type": memory_type,
                    "title": title,
                    "content": content,
                    "importance": importance
                }
            )
        except Exception as e:
            logger.error(f"Error updating user memory: {e}")
            return False
    
    def get_coach_status(self, user_id: str, context: CoachingContext) -> Dict[str, Any]:
        """Get coach status and relationship metrics"""
        try:
            # Determine coach status based on context
            if context.current_streak >= 7:
                status = "Impressed"
                status_color = "success"
            elif context.current_streak >= 3:
                status = "Waiting for you"
                status_color = "primary"
            else:
                status = "Concerned"
                status_color = "warning"
            
            # Calculate relationship metrics
            relationship_score = self._calculate_relationship_score(context, context.current_streak)
            
            return {
                "status": status,
                "status_color": status_color,
                "user_id": user_id,
                "relationship_stage": context.relationship_stage,
                "attachment_level": context.attachment_level,
                "relationship_score": relationship_score,
                "coach_available": True,
                "last_interaction": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting coach status: {e}")
            return {
                "status": "Unavailable",
                "status_color": "error",
                "user_id": user_id,
                "coach_available": False
            }
    
    def get_signature_phrases(self, category: str) -> List[str]:
        """Get coach signature phrases by category"""
        phrase_bank = {
            "accountability_openers": [
                "What's the plan",
                "What u gonna do about it", 
                "What's different this time",
                "What commitment u making"
            ],
            "encouragement": [
                "U got this bro",
                "Good luck lil bro", 
                "believe in u bro",
                "Safee"
            ],
            "challenging_questions": [
                "But u said this mattered. What's the plan?",
                "U keep saying this, so likee What's different now?",
                "What exactly u gna do today?"
            ]
        }
        
        return phrase_bank.get(category, ["What's the plan bro?"])
    
    def analyze_user_pattern(self, message: str) -> Dict[str, Any]:
        """Analyze user message for coaching approach"""
        message_lower = message.lower()
        
        # Simple pattern analysis
        if any(word in message_lower for word in ["unmotivated", "tired", "struggling"]):
            pattern = {"approach": "energy_building", "pressure": "gentle"}
        elif any(word in message_lower for word in ["missed", "failed", "didn't"]):
            pattern = {"approach": "accountability", "pressure": "direct"}
        elif any(word in message_lower for word in ["want to", "going to", "planning"]):
            pattern = {"approach": "commitment_focus", "pressure": "supportive"}
        else:
            pattern = {"approach": "general_check", "pressure": "balanced"}
        
        return {
            "message": message,
            "analysis": pattern,
            "success": True
        }
    
    # Private helper methods
    
    def _build_instructions(self, response_type: CoachingResponseType, context: Optional[Dict[str, Any]]) -> str:
        """Build assistant instructions based on response type"""
        # Define instructions map inside method to avoid circular import issues
        instructions_map = {
            "greeting": "Give a brief, personalized greeting. Keep it under 20 words.",
            "check_in": "Ask a direct check-in question. Reference their streak if applicable.",
            "pressure": "Apply gentle pressure. Be direct but supportive.",
            "coaching": "Provide accountability coaching. Ask follow-up questions.",
            "celebration": "Acknowledge progress and build momentum.",
            "support": "Offer support and ask what they need.",
            "advice": "Provide specific coaching advice based on context.",
            "stats": "Provide coaching statistics and insights.",
            "insights": "Analyze patterns and provide coaching insights."
        }
        
        base_instruction = instructions_map.get(response_type.value if hasattr(response_type, 'value') else str(response_type), "Provide helpful accountability coaching.")
        
        if context:
            context_str = f" Context: {json.dumps(context)}"
            return f"{base_instruction}{context_str}"
        
        return base_instruction
    
    def _calculate_personality_score(self, response_type: CoachingResponseType) -> float:
        """Calculate personality score based on response type"""
        # Define score map inside method to avoid circular import issues
        score_map = {
            "greeting": 0.6,
            "check_in": 0.7,
            "pressure": 0.9,
            "coaching": 0.8,
            "celebration": 0.7,
            "support": 0.8,
            "advice": 0.85,
            "stats": 0.6,
            "insights": 0.9
        }
        
        return score_map.get(response_type.value if hasattr(response_type, 'value') else str(response_type), 0.7)
    
    async def _get_coaching_context(self, user_id: str) -> Dict[str, Any]:
        """Get coaching-specific context"""
        try:
            # This would query additional coaching-specific tables
            # For now, return defaults
            return {
                "attachment_level": "initial",
                "relationship_stage": "initial",
                "communication_preferences": {},
                "health_context": {},
                "time_context": {}
            }
        except Exception as e:
            logger.error(f"Error getting coaching context: {e}")
            return {
                "attachment_level": "initial",
                "relationship_stage": "initial",
                "communication_preferences": {},
                "health_context": {},
                "time_context": {}
            }
    
    async def _analyze_coaching_patterns(self, user_id: str) -> Dict[str, Any]:
        """Analyze coaching patterns"""
        try:
            # Analyze conversation patterns, engagement, etc.
            return {
                "engagement_trend": "stable",
                "response_quality": "good",
                "accountability_readiness": "high",
                "pattern_consistency": "improving"
            }
        except Exception as e:
            logger.error(f"Error analyzing coaching patterns: {e}")
            return {}
    
    def _calculate_engagement_level(self, usage_stats: Dict[str, Any]) -> str:
        """Calculate user engagement level"""
        messages_used = usage_stats.get('messages_used', 0)
        if messages_used > 50:
            return "high"
        elif messages_used > 20:
            return "medium"
        else:
            return "low"
    
    def _calculate_streak_progress(self, context: CoachingContext) -> Dict[str, Any]:
        """Calculate streak progress metrics"""
        return {
            "current": context.current_streak,
            "longest": context.longest_streak,
            "progress_percentage": min((context.current_streak / max(context.longest_streak, 1)) * 100, 100),
            "next_milestone": context.current_streak + 1
        }
    
    def _calculate_commitment_adherence(self, context: CoachingContext) -> float:
        """Calculate commitment adherence score"""
        if not context.active_commitments:
            return 0.5
        return min(len(context.active_commitments) * 0.2, 1.0)
    
    def _calculate_effectiveness(self, usage_stats: Dict[str, Any]) -> float:
        """Calculate coaching effectiveness score"""
        messages_used = usage_stats.get('messages_used', 0)
        is_pro = usage_stats.get('is_pro', False)
        
        base_score = 0.5
        if messages_used > 30:
            base_score += 0.3
        if is_pro:
            base_score += 0.2
        
        return min(base_score, 1.0)
    
    def _calculate_relationship_score(self, context: CoachingContext, streak: int) -> float:
        """Calculate relationship score between user and coach"""
        base_score = 0.5
        
        # Add streak bonus
        base_score += min(streak * 0.05, 0.3)
        
        # Add commitment bonus
        base_score += min(len(context.active_commitments) * 0.1, 0.2)
        
        return min(base_score, 1.0)
    
    def _generate_recommendations(self, context: CoachingContext, usage_stats: Dict[str, Any], patterns: Dict[str, Any]) -> List[str]:
        """Generate coaching recommendations"""
        recommendations = []
        
        if context.current_streak < 3:
            recommendations.append("Focus on building consistency with daily check-ins")
        
        if not context.active_commitments:
            recommendations.append("Set 1-2 specific, achievable commitments")
        
        if usage_stats.get('messages_used', 0) < 10:
            recommendations.append("Engage more with the coach for better results")
        
        if patterns.get('engagement_trend') == 'declining':
            recommendations.append("Try varying your coaching approach")
        
        if not recommendations:
            recommendations.append("Keep up the great work!")
        
        return recommendations


# Global unified coaching service instance
unified_coaching_service = UnifiedCoachingService()