"""
Model Router - Cost Optimization for Assistant-Native Architecture
Routes requests to appropriate models based on complexity and type
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import re

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """Types of coach messages for routing decisions"""
    GREETING = "greeting"
    CHECK_IN = "check_in"
    PRESSURE = "pressure"
    CELEBRATION = "celebration"
    SUPPORT = "support"
    DEEP_COACHING = "deep_coaching"
    PATTERN_ANALYSIS = "pattern_analysis"
    GOAL_SETTING = "goal_setting"
    ACCOUNTABILITY = "accountability"

class ModelTier(Enum):
    """Model tiers for cost optimization"""
    CHEAP = "cheap"      # gpt-4o-mini, gpt-3.5-turbo
    PREMIUM = "premium"  # gpt-4, gpt-4-turbo

class ModelRouter:
    """
    Intelligent model routing for cost optimization.
    
    Routes 80% of traffic to cheap models, 20% to premium.
    """
    
    def __init__(self):
        # Model configurations
        self.models = {
            ModelTier.CHEAP: {
                "primary": "gpt-4o-mini",
                "fallback": "gpt-3.5-turbo",
                "cost_per_1k_tokens": 0.00015,  # Approximate
                "max_tokens": 150,
                "temperature": 0.7
            },
            ModelTier.PREMIUM: {
                "primary": "gpt-4",
                "fallback": "gpt-4-turbo",
                "cost_per_1k_tokens": 0.03,  # Approximate
                "max_tokens": 300,
                "temperature": 0.8
            }
        }
        
        # Message type routing rules
        self.routing_rules = {
            MessageType.GREETING: ModelTier.CHEAP,
            MessageType.CHECK_IN: ModelTier.CHEAP,
            MessageType.PRESSURE: ModelTier.CHEAP,
            MessageType.CELEBRATION: ModelTier.CHEAP,
            MessageType.SUPPORT: ModelTier.CHEAP,
            MessageType.DEEP_COACHING: ModelTier.PREMIUM,
            MessageType.PATTERN_ANALYSIS: ModelTier.PREMIUM,
            MessageType.GOAL_SETTING: ModelTier.PREMIUM,
            MessageType.ACCOUNTABILITY: ModelTier.PREMIUM
        }
    
    def classify_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> MessageType:
        """
        Classify message type for routing decisions.
        
        Uses keyword analysis and context to determine complexity.
        """
        message_lower = message.lower()
        
        # Simple patterns for cheap models
        cheap_indicators = [
            r'\b(hi|hello|hey|good morning|good afternoon|good evening)\b',
            r'\b(how are you|how\'s it going|what\'s up|what\'s good)\b',
            r'\b(ok|okay|yeah|yes|no|thanks)\b',
            r'\b(good job|nice work|well done|keep going)\b',
            r'\b(talk to me|what\'s the plan|locks? in)\b'
        ]
        
        # Complex patterns for premium models
        premium_indicators = [
            r'\b(analyze|pattern|trend|why do i|help me understand)\b',
            r'\b(goal|objective|plan|strategy|approach)\b',
            r'\b(struggle|stuck|overwhelm|confused|lost)\b',
            r'\b(motivation|purpose|meaning|why am i)\b',
            r'\b(breakthrough|insight|realize|understand)\b',
            r'\b(procrastination|avoidance|resistance)\b'
        ]
        
        # Check for premium indicators first
        for pattern in premium_indicators:
            if re.search(pattern, message_lower):
                if any(word in message_lower for word in ['analyze', 'pattern', 'trend', 'why do i']):
                    return MessageType.PATTERN_ANALYSIS
                elif any(word in message_lower for word in ['goal', 'objective', 'plan', 'strategy']):
                    return MessageType.GOAL_SETTING
                elif any(word in message_lower for word in ['struggle', 'stuck', 'overwhelm', 'confused']):
                    return MessageType.DEEP_COACHING
                else:
                    return MessageType.DEEP_COACHING
        
        # Check for cheap indicators
        for pattern in cheap_indicators:
            if re.search(pattern, message_lower):
                if any(word in message_lower for word in ['hi', 'hello', 'hey', 'good morning']):
                    return MessageType.GREETING
                elif any(word in message_lower for word in ['how are you', 'how\'s it going', 'what\'s up']):
                    return MessageType.CHECK_IN
                elif any(word in message_lower for word in ['good job', 'nice work', 'well done']):
                    return MessageType.CELEBRATION
                else:
                    return MessageType.CHECK_IN
        
        # Context-based classification
        if context:
            # Check user state for complexity indicators
            user_state = context.get('user_state', {})
            
            if user_state.get('current_streak', 0) >= 7:
                # Long streak users often want deeper coaching
                return MessageType.DEEP_COACHING
            
            recent_pattern = user_state.get('recent_pattern', '')
            if recent_pattern in ['struggling', 'slipping']:
                return MessageType.SUPPORT
            elif recent_pattern == 'locked_in':
                return MessageType.CELEBRATION
        
        # Default to cheap for short, simple messages
        if len(message.split()) <= 5:
            return MessageType.CHECK_IN
        
        # Default to premium for longer, complex messages
        return MessageType.DEEP_COACHING
    
    def select_model(self, message_type: MessageType, user_id: str) -> Tuple[str, Dict[str, Any]]:
        """
        Select appropriate model and configuration.
        
        Returns (model_name, model_config)
        """
        tier = self.routing_rules.get(message_type, ModelTier.CHEAP)
        config = self.models[tier].copy()
        
        # Add routing metadata
        config.update({
            "message_type": message_type.value,
            "tier": tier.value,
            "user_id": user_id,
            "routing_reason": self._get_routing_reason(message_type, tier)
        })
        
        return config["primary"], config
    
    def _get_routing_reason(self, message_type: MessageType, tier: ModelTier) -> str:
        """Get human-readable reason for routing decision"""
        reasons = {
            MessageType.GREETING: "Simple greeting - using cost-effective model",
            MessageType.CHECK_IN: "Quick status check - using fast model",
            MessageType.PRESSURE: "Short accountability message - using efficient model",
            MessageType.CELEBRATION: "Positive reinforcement - using lightweight model",
            MessageType.SUPPORT: "Supportive message - using responsive model",
            MessageType.DEEP_COACHING: "Complex coaching - using premium model for better reasoning",
            MessageType.PATTERN_ANALYSIS: "Pattern analysis - using advanced model",
            MessageType.GOAL_SETTING: "Goal planning - using capable model",
            MessageType.ACCOUNTABILITY: "Deep accountability - using sophisticated model"
        }
        
        return reasons.get(message_type, f"Default routing to {tier.value} model")
    
    def estimate_cost(self, message_type: MessageType, message_length: int) -> Dict[str, float]:
        """
        Estimate cost for the request.
        
        Returns cost estimates for different scenarios.
        """
        tier = self.routing_rules.get(message_type, ModelTier.CHEAP)
        model_config = self.models[tier]
        
        # Rough token estimates
        input_tokens = max(50, message_length // 4)  # Rough estimate
        output_tokens = model_config["max_tokens"]
        total_tokens = input_tokens + output_tokens
        
        cost_per_1k = model_config["cost_per_1k_tokens"]
        estimated_cost = (total_tokens / 1000) * cost_per_1k
        
        # Calculate potential savings vs premium model
        if tier == ModelTier.CHEAP:
            premium_cost = (total_tokens / 1000) * self.models[ModelTier.PREMIUM]["cost_per_1k_tokens"]
            savings = premium_cost - estimated_cost
        else:
            savings = 0
        
        return {
            "estimated_cost": estimated_cost,
            "tier": tier.value,
            "total_tokens": total_tokens,
            "potential_savings": savings,
            "savings_percentage": (savings / (estimated_cost + savings)) * 100 if tier == ModelTier.CHEAP else 0
        }
    
    def should_use_assistant_api(self, message_type: MessageType) -> bool:
        """
        Determine if this request should use Assistant API or direct completion.
        
        Assistant API is better for:
        - Complex conversations
        - Memory retention
        - Function calling
        """
        assistant_types = [
            MessageType.DEEP_COACHING,
            MessageType.PATTERN_ANALYSIS,
            MessageType.GOAL_SETTING,
            MessageType.ACCOUNTABILITY
        ]
        
        return message_type in assistant_types
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get routing optimization statistics"""
        total_message_types = len(MessageType)
        cheap_types = sum(1 for mt in MessageType if self.routing_rules.get(mt) == ModelTier.CHEAP)
        premium_types = total_message_types - cheap_types
        
        return {
            "total_message_types": total_message_types,
            "cheap_routing_percentage": (cheap_types / total_message_types) * 100,
            "premium_routing_percentage": (premium_types / total_message_types) * 100,
            "cost_optimization_target": "80% traffic to cheap models",
            "routing_rules": {mt.value: tier.value for mt, tier in self.routing_rules.items()}
        }

# Global model router instance
model_router = ModelRouter()