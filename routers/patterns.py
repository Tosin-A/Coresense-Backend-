"""
Pattern Recognition API Router
Handles pattern analysis and insights generation
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from backend.services.pattern_recognition import pattern_recognition_service, DetectedPattern
from backend.database.supabase_client import get_supabase_client
from backend.utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/patterns", tags=["patterns"])


class PatternResponse(BaseModel):
    pattern_type: str
    description: str
    strength: str
    confidence: float
    data_points: List[Dict[str, Any]]
    actionable_insights: List[str]
    detected_at: str


class PatternAnalysisResponse(BaseModel):
    success: bool
    patterns: List[PatternResponse]
    total_patterns: int
    analysis_date: str
    user_id: str


@router.get("/analyze/{user_id}", response_model=PatternAnalysisResponse)
async def analyze_user_patterns(
    user_id: str,
    days_back: int = Query(30, ge=7, le=365, description="Number of days to analyze"),
    user_id_param: str = Query(None, description="Alternative user ID parameter")
):
    """Analyze user behavior patterns over specified time period"""
    try:
        # Use provided user_id_param or fall back to path parameter
        actual_user_id = user_id_param or user_id
        
        # Analyze patterns
        patterns = await pattern_recognition_service.analyze_user_patterns(
            user_id=actual_user_id, 
            days_back=days_back
        )
        
        # Convert to response format
        pattern_responses = []
        for pattern in patterns:
            pattern_responses.append(PatternResponse(
                pattern_type=pattern.pattern_type.value,
                description=pattern.description,
                strength=pattern.strength.value,
                confidence=pattern.confidence,
                data_points=pattern.data_points,
                actionable_insights=pattern.actionable_insights,
                detected_at=pattern.detected_at.isoformat()
            ))
        
        return PatternAnalysisResponse(
            success=True,
            patterns=pattern_responses,
            total_patterns=len(pattern_responses),
            analysis_date=datetime.now().isoformat(),
            user_id=actual_user_id
        )
        
    except Exception as e:
        logger.error(f"Error analyzing patterns for {user_id}: {e}")
        raise DatabaseError("Failed to analyze patterns", original_error=e)


@router.get("/summary/{user_id}")
async def get_pattern_summary(
    user_id: str,
    user_id_param: str = Query(None, description="Alternative user ID parameter")
):
    """Get a summary of detected patterns for a user"""
    try:
        actual_user_id = user_id_param or user_id
        
        # Analyze patterns
        patterns = await pattern_recognition_service.analyze_user_patterns(
            user_id=actual_user_id, 
            days_back=30
        )
        
        if not patterns:
            return {
                "success": True,
                "summary": "No clear patterns detected yet. Keep using the app to build your behavioral profile.",
                "pattern_count": 0,
                "strongest_patterns": [],
                "recommendations": [
                    "Use the app regularly to establish patterns",
                    "Set and track commitments to see completion patterns",
                    "Maintain conversations with your coach for response analysis"
                ]
            }
        
        # Sort by confidence
        sorted_patterns = sorted(patterns, key=lambda p: p.confidence, reverse=True)
        
        # Create summary
        strongest_patterns = []
        recommendations = []
        
        for pattern in sorted_patterns[:3]:  # Top 3 patterns
            strongest_patterns.append({
                "type": pattern.pattern_type.value,
                "description": pattern.description,
                "confidence": pattern.confidence,
                "strength": pattern.strength.value
            })
            
            # Add specific recommendations based on pattern type
            if pattern.pattern_type.value == "usage_pattern":
                if "Sporadic" in pattern.description:
                    recommendations.append("Try to establish a more consistent daily routine")
                elif "Daily" in pattern.description:
                    recommendations.append("Great job maintaining daily consistency!")
            
            elif pattern.pattern_type.value == "response_pattern":
                if "Slow" in pattern.description:
                    recommendations.append("Consider checking in more frequently with your coach")
                elif "Quick" in pattern.description:
                    recommendations.append("Your quick responses show strong engagement")
            
            elif pattern.pattern_type.value == "streak_pattern":
                if "Long-term consistency" in pattern.description:
                    recommendations.append("You're doing excellent at maintaining long-term habits")
                elif "Starting streak" in pattern.description:
                    recommendations.append("Focus on building momentum with your current streak")
        
        # Add general recommendations
        if not recommendations:
            recommendations = [
                "Continue using the app to strengthen pattern detection",
                "Engage regularly with your coach for personalized insights",
                "Set commitments to analyze your follow-through patterns"
            ]
        
        return {
            "success": True,
            "summary": f"Detected {len(patterns)} behavioral patterns with {sorted_patterns[0].strength.value} confidence",
            "pattern_count": len(patterns),
            "strongest_patterns": strongest_patterns,
            "recommendations": recommendations[:5]  # Limit to 5 recommendations
        }
        
    except Exception as e:
        logger.error(f"Error getting pattern summary for {user_id}: {e}")
        raise DatabaseError("Failed to get pattern summary", original_error=e)


@router.get("/insights/{user_id}")
async def generate_pattern_insights(
    user_id: str,
    user_id_param: str = Query(None, description="Alternative user ID parameter")
):
    """Generate actionable insights based on detected patterns"""
    try:
        actual_user_id = user_id_param or user_id
        
        # Analyze patterns
        patterns = await pattern_recognition_service.analyze_user_patterns(
            user_id=actual_user_id, 
            days_back=30
        )
        
        insights = []
        
        # Process each pattern to create actionable insights
        for pattern in patterns:
            for insight in pattern.actionable_insights:
                insights.append({
                    "type": "pattern_insight",
                    "category": pattern.pattern_type.value,
                    "message": insight,
                    "confidence": pattern.confidence,
                    "strength": pattern.strength.value,
                    "data_points": pattern.data_points,
                    "priority": "high" if pattern.confidence >= 0.8 else "medium" if pattern.confidence >= 0.6 else "low"
                })
        
        # Sort by priority and confidence
        priority_order = {"high": 3, "medium": 2, "low": 1}
        insights.sort(key=lambda x: (priority_order.get(x["priority"], 0), x["confidence"]), reverse=True)
        
        return {
            "success": True,
            "insights": insights,
            "total_insights": len(insights),
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating pattern insights for {user_id}: {e}")
        raise DatabaseError("Failed to generate pattern insights", original_error=e)


@router.post("/test-analysis")
async def test_pattern_analysis():
    """Test endpoint for pattern analysis with sample data"""
    try:
        # This would typically test with a sample user ID
        # For now, return a success message
        return {
            "success": True,
            "message": "Pattern analysis service is ready",
            "supported_patterns": [
                "usage_pattern",
                "response_pattern", 
                "time_pattern",
                "commitment_pattern",
                "streak_pattern",
                "engagement_pattern"
            ],
            "test_instructions": "Use /analyze/{user_id} endpoint with a real user ID to test pattern analysis"
        }
        
    except Exception as e:
        logger.error(f"Error in test pattern analysis: {e}")
        raise DatabaseError("Pattern analysis test failed", original_error=e)


@router.get("/health")
async def pattern_service_health():
    """Health check for pattern recognition service"""
    try:
        return {
            "service": "pattern_recognition",
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        }
        
    except Exception as e:
        logger.error(f"Pattern service health check failed: {e}")
        return {
            "service": "pattern_recognition",
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }