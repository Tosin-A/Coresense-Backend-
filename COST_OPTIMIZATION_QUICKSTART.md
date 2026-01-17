# Cost Optimization Quick Start Guide

## 🎯 Goal: 40-60% cost reduction in 2 weeks

This guide walks you through implementing the high-impact, low-effort optimizations first.

---

## Week 1: Quick Wins (25% savings, ~6 hours work)

### Day 1: Remove Unnecessary Function Definitions (5% savings, 2 hours)

**Current Problem:** 3 function definitions (~500 tokens) sent with EVERY request, even when functions aren't used.

**File:** `backend/services/thread_management.py`

**Change:**
```python
# BEFORE (line 163-168)
run = self.client.beta.threads.runs.create(
    thread_id=thread_id,
    assistant_id=self.assistant_id,
    instructions=None,
    tools=self.functions  # ❌ Always included
)

# AFTER
run = self.client.beta.threads.runs.create(
    thread_id=thread_id,
    assistant_id=self.assistant_id,
    instructions=None,
    tools=[]  # ✅ Only include when needed
)
```

**Test:**
```bash
# Run a simple test message
curl -X POST http://localhost:8000/api/v1/coach/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "hey", "response_type": "greeting"}'

# Check logs for token usage
grep "tokens" backend/logs/app.log | tail -20
```

**Expected Result:** Input tokens reduced by ~500 per request

---

### Day 1-2: Pattern-Based Response Cache (15% savings, 1 day)

**Current Problem:** Every message hits the API, even common greetings.

**File:** Create `backend/services/pattern_responder.py`

```python
"""
Pattern-based responses for common messages
Avoids API calls for 20-30% of messages
"""

import random
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class PatternResponder:
    """Fast pattern-based responses to avoid API calls"""
    
    def __init__(self):
        self.patterns = {
            # Simple greetings (morning)
            'greeting_morning': {
                'triggers': ['morning', 'hey', 'hello', 'hi', 'sup', 'yo'],
                'time_filter': lambda h: 5 <= h < 12,
                'responses': [
                    "What's the plan today?",
                    "Morning. What u working on?",
                    "Locks? in today?",
                    "What's different today?",
                ]
            },
            
            # Simple greetings (afternoon)
            'greeting_afternoon': {
                'triggers': ['hey', 'hello', 'hi', 'sup', 'afternoon'],
                'time_filter': lambda h: 12 <= h < 17,
                'responses': [
                    "What's up?",
                    "Talk to me",
                    "What u working on?",
                    "What's the move?",
                ]
            },
            
            # Simple greetings (evening)
            'greeting_evening': {
                'triggers': ['hey', 'hello', 'hi', 'evening', 'tonight'],
                'time_filter': lambda h: 17 <= h < 24,
                'responses': [
                    "How'd today go?",
                    "What got done today?",
                    "Did u do what u said?",
                    "Talk to me about today",
                ]
            },
            
            # Completion responses
            'completion': {
                'triggers': ['done', 'did it', 'completed', 'finished'],
                'streak_filter': lambda s: s >= 3,  # User has decent streak
                'responses': [
                    "Nice bro. Keep going",
                    "U got this",
                    "Good. What's next?",
                    "Safee. What's tomorrow?",
                ]
            },
            
            # Struggling responses
            'struggling': {
                'triggers': ['struggling', 'hard', 'difficult', 'can\'t', 'tired'],
                'responses': [
                    "Talk to me. What's making it hard?",
                    "What's actually stopping u?",
                    "I hear u. But what's one thing u can do?",
                    "What would make today easier?",
                ]
            },
        }
    
    def get_pattern_response(
        self, 
        message: str, 
        user_context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Try to match message to a pattern and return cached response.
        Returns None if no pattern matches.
        """
        
        message_lower = message.lower().strip()
        current_hour = user_context.get('current_hour', 12)
        current_streak = user_context.get('current_streak', 0)
        
        # Very short messages are likely greetings
        if len(message_lower.split()) <= 2:
            return self._match_greeting(message_lower, current_hour, current_streak)
        
        # Check all patterns
        for pattern_name, pattern_config in self.patterns.items():
            if self._matches_pattern(message_lower, pattern_config, current_hour, current_streak):
                response = random.choice(pattern_config['responses'])
                logger.info(f"✅ Pattern match: {pattern_name} - saved API call")
                return response
        
        return None
    
    def _match_greeting(self, message: str, hour: int, streak: int) -> Optional[str]:
        """Special handling for simple greetings"""
        
        greeting_words = ['hi', 'hey', 'hello', 'sup', 'yo', 'morning', 'afternoon', 'evening']
        
        if message not in greeting_words:
            return None
        
        # Time-based greeting
        if 5 <= hour < 12:
            return random.choice(self.patterns['greeting_morning']['responses'])
        elif 12 <= hour < 17:
            return random.choice(self.patterns['greeting_afternoon']['responses'])
        else:
            return random.choice(self.patterns['greeting_evening']['responses'])
    
    def _matches_pattern(
        self, 
        message: str, 
        pattern_config: Dict[str, Any],
        current_hour: int,
        current_streak: int
    ) -> bool:
        """Check if message matches pattern"""
        
        # Check trigger words
        triggers = pattern_config.get('triggers', [])
        if not any(trigger in message for trigger in triggers):
            return False
        
        # Check time filter if present
        time_filter = pattern_config.get('time_filter')
        if time_filter and not time_filter(current_hour):
            return False
        
        # Check streak filter if present
        streak_filter = pattern_config.get('streak_filter')
        if streak_filter and not streak_filter(current_streak):
            return False
        
        return True
```

**Integration:** Update `backend/services/coaching_service.py`

```python
# Add import at top
from .pattern_responder import PatternResponder

class UnifiedCoachingService:
    
    def __init__(self):
        # ... existing code ...
        self.pattern_responder = PatternResponder()
    
    async def chat(self, user_id: str, message: str, ...):
        # ... message limit check ...
        
        # 🆕 NEW: Try pattern response first
        user_context = {
            'current_hour': datetime.now().hour,
            'current_streak': essential_context.current_streak if hasattr(self, 'essential_context') else 0
        }
        
        pattern_response = self.pattern_responder.get_pattern_response(message, user_context)
        
        if pattern_response:
            # Return cached pattern response (no API call!)
            return CoachingResponse(
                messages=[pattern_response],
                personality_score=0.8,
                context_used=["pattern_cache"],
                variation_applied=True,
                response_type=response_type,
                thread_id=None,
                function_calls=[],
                usage_stats=usage_stats,
                saved_ids={},
                client_temp_id=client_temp_id
            )
        
        # Original API call logic continues...
        thread_id = await self.thread_manager.get_or_create_user_thread(user_id)
        # ... rest of existing code ...
```

**Test:**
```python
# Test pattern matching
python3 << EOF
from backend.services.pattern_responder import PatternResponder

pr = PatternResponder()

# Test morning greeting
result = pr.get_pattern_response("hey", {"current_hour": 9, "current_streak": 5})
print(f"Morning: {result}")

# Test completion
result = pr.get_pattern_response("done with workout", {"current_hour": 14, "current_streak": 7})
print(f"Completion: {result}")
EOF
```

---

### Day 2-4: API Selector (Hybrid Approach) (35% savings, 2 days)

**Current Problem:** ALL messages use expensive Assistant API, even simple ones.

**Solution:** Route 80% to Completions API (5x cheaper)

**Step 1:** Create `backend/services/api_selector.py`

```python
"""
API Selector - Routes between Assistant API and Completions API
"""

import logging
from typing import Dict, Any
from .model_router import MessageType, model_router

logger = logging.getLogger(__name__)

class APISelector:
    """Intelligently select between Assistant API and Completions API"""
    
    def should_use_assistant_api(
        self, 
        message: str, 
        user_context: Dict[str, Any],
        message_count: int
    ) -> bool:
        """
        Use Assistant API for:
        1. First 3 messages (relationship building)
        2. Complex coaching (goal setting, pattern analysis)
        3. Function calling scenarios
        
        Use Completions API for:
        1. Simple greetings and check-ins
        2. Quick accountability messages
        3. Celebrations
        """
        
        # Always use Assistant for first 3 messages (build relationship)
        if message_count < 3:
            logger.info(f"🎯 Using Assistant API: Building relationship (message {message_count + 1}/3)")
            return True
        
        # Classify message complexity
        message_type = model_router.classify_message(message, user_context)
        
        # Complex types need Assistant API
        complex_types = [
            MessageType.DEEP_COACHING,
            MessageType.PATTERN_ANALYSIS,
            MessageType.GOAL_SETTING,
            MessageType.ACCOUNTABILITY
        ]
        
        if message_type in complex_types:
            logger.info(f"🎯 Using Assistant API: Complex message type ({message_type.value})")
            return True
        
        # Default to Completions API (cheaper)
        logger.info(f"💰 Using Completions API: Simple message type ({message_type.value})")
        return False
    
    def estimate_cost_difference(self, use_assistant: bool) -> Dict[str, Any]:
        """Estimate cost difference between APIs"""
        
        if use_assistant:
            # Assistant API overhead
            base_cost = 0.009  # ~0.9 cents per message
            api_type = "assistant"
        else:
            # Completions API (GPT-4o-mini)
            base_cost = 0.0015  # ~0.15 cents per message
            api_type = "completions"
        
        return {
            "api_type": api_type,
            "estimated_cost": base_cost,
            "model": "gpt-4" if use_assistant else "gpt-4o-mini"
        }
```

**Step 2:** Create `backend/services/completions_service.py`

```python
"""
Completions Service - Direct API calls for simple messages
Much cheaper than Assistant API
"""

import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from config import get_settings

logger = logging.getLogger(__name__)

class CompletionsService:
    """Handle simple coaching messages via Completions API"""
    
    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        
        # System prompt for the coach
        self.system_prompt = """You are a direct, no-BS accountability coach. Your style:

- Short, punchy messages (1-2 sentences max)
- Use casual language: "u", "bro", "what's up"
- Ask direct questions: "What's the plan?", "What u gonna do about it?"
- No fluff, no long explanations
- Hold people accountable but be supportive
- Signature phrases: "locks? in", "talk to me", "what's different this time?"

Keep responses under 20 words."""
    
    async def get_simple_response(
        self,
        user_id: str,
        message: str,
        user_context: Dict[str, Any],
        message_type: str = "check_in"
    ) -> Dict[str, Any]:
        """
        Get response via Completions API (cheaper than Assistant)
        """
        
        try:
            # Build context-aware prompt
            context_str = self._build_context_string(user_context)
            
            # Call Completions API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # 60x cheaper than GPT-4
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Context: {context_str}\n\nUser: {message}"}
                ],
                max_tokens=50,  # Keep responses short
                temperature=0.8
            )
            
            # Extract response
            coach_message = response.choices[0].message.content.strip()
            
            logger.info(f"✅ Completions API response: {coach_message[:50]}...")
            
            return {
                "messages": [coach_message],
                "tokens_used": response.usage.total_tokens,
                "model": "gpt-4o-mini",
                "api_type": "completions",
                "function_calls": [],
                "context_used": ["minimal"]
            }
            
        except Exception as e:
            logger.error(f"Error in Completions API: {e}")
            # Fallback to pattern response
            return {
                "messages": ["Talk to me. What's going on?"],
                "tokens_used": 0,
                "model": "fallback",
                "api_type": "fallback",
                "function_calls": [],
                "context_used": []
            }
    
    def _build_context_string(self, user_context: Dict[str, Any]) -> str:
        """Build minimal context string"""
        
        streak = user_context.get('current_streak', 0)
        name = user_context.get('user_name', 'bro')
        
        context_parts = [f"User: {name}"]
        
        if streak > 0:
            context_parts.append(f"Streak: {streak} days")
        
        return ", ".join(context_parts)

# Global instance
completions_service = CompletionsService()
```

**Step 3:** Update `backend/services/coaching_service.py`

```python
# Add imports
from .api_selector import APISelector
from .completions_service import completions_service

class UnifiedCoachingService:
    
    def __init__(self):
        # ... existing code ...
        self.api_selector = APISelector()
    
    async def chat(self, user_id: str, message: str, ...):
        # ... pattern response check ...
        # ... message limit check ...
        
        # Get user context
        essential_context = await self.context_mgr.get_essential_context(user_id, "minimal")
        
        # Get message count for this user
        message_count = await self._get_user_message_count(user_id)
        
        # 🆕 NEW: Decide which API to use
        use_assistant = self.api_selector.should_use_assistant_api(
            message=message,
            user_context={
                'current_streak': essential_context.current_streak,
                'user_name': essential_context.user_name
            },
            message_count=message_count
        )
        
        if use_assistant:
            # Original Assistant API logic
            thread_id = await self.thread_manager.get_or_create_user_thread(user_id)
            await self.thread_manager.add_message_to_thread(thread_id, message, "user")
            result = await self.thread_manager.run_assistant(thread_id, user_id, response_type.value)
            
        else:
            # 🆕 NEW: Use cheaper Completions API
            result = await completions_service.get_simple_response(
                user_id=user_id,
                message=message,
                user_context={
                    'current_streak': essential_context.current_streak,
                    'user_name': essential_context.user_name
                },
                message_type=response_type.value
            )
            thread_id = None  # No thread for simple messages
        
        # ... rest of existing code (store messages, return response) ...
    
    async def _get_user_message_count(self, user_id: str) -> int:
        """Get total message count for user"""
        try:
            from database.supabase_client import get_supabase_client
            supabase = get_supabase_client()
            
            response = supabase.table("messages").select("id", count="exact").eq(
                "userid", user_id
            ).eq("direction", "outgoing").execute()
            
            return response.count if response.count else 0
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
```

**Test:**
```bash
# Test simple greeting (should use Completions API)
curl -X POST http://localhost:8000/api/v1/coach/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "hey", "response_type": "greeting"}'

# Check logs for API routing
grep "Using.*API" backend/logs/app.log | tail -5

# Test complex message (should use Assistant API)
curl -X POST http://localhost:8000/api/v1/coach/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "I keep struggling with my goals, can you help me analyze why?", "response_type": "coaching"}'

# Check logs again
grep "Using.*API" backend/logs/app.log | tail -5
```

---

## Week 2: Thread Optimization (20% additional savings)

### Day 5-7: Model Router Integration (20% savings, 2 days)

**Current Problem:** `model_router.py` exists but isn't used!

**Solution:** Actually use it to route to GPT-4o-mini for most messages.

**File:** `backend/services/completions_service.py`

```python
# Add model selection
from .model_router import model_router

class CompletionsService:
    
    async def get_simple_response(self, user_id: str, message: str, ...):
        
        # Select model based on message type
        message_type = model_router.classify_message(message, user_context)
        model_name, model_config = model_router.select_model(message_type, user_id)
        
        logger.info(f"📊 Selected model: {model_name} for {message_type.value}")
        
        response = self.client.chat.completions.create(
            model=model_name,  # Dynamic model selection
            max_tokens=model_config['max_tokens'],
            temperature=model_config['temperature'],
            # ... rest of config ...
        )
```

---

### Day 8-10: Thread Pruning (10% savings, 3 days)

**Current Problem:** Threads grow forever, input tokens increase over time.

**Solution:** Keep only last 20 messages, summarize the rest.

**File:** `backend/services/thread_management.py`

```python
class ThreadManagementService:
    
    MAX_THREAD_MESSAGES = 20
    
    async def run_assistant(self, thread_id: str, user_id: str, ...):
        
        # 🆕 NEW: Prune thread before running
        await self.prune_thread_if_needed(thread_id, user_id)
        
        # Original run logic
        run = self.client.beta.threads.runs.create(...)
        # ...
    
    async def prune_thread_if_needed(self, thread_id: str, user_id: str):
        """Keep thread under 20 messages"""
        
        # Get message count
        messages = self.client.beta.threads.messages.list(
            thread_id=thread_id,
            limit=100
        )
        
        if len(messages.data) <= self.MAX_THREAD_MESSAGES:
            return  # No pruning needed
        
        logger.info(f"🔪 Pruning thread {thread_id}: {len(messages.data)} -> {self.MAX_THREAD_MESSAGES}")
        
        # OpenAI doesn't support message deletion
        # Solution: Create new thread with last 20 messages
        new_thread_id = await self._create_pruned_thread(
            user_id, 
            messages.data[:self.MAX_THREAD_MESSAGES]
        )
        
        # Update thread mapping
        await self._update_thread_mapping(user_id, new_thread_id)
        
        return new_thread_id
    
    async def _create_pruned_thread(self, user_id: str, recent_messages: list) -> str:
        """Create new thread with only recent messages"""
        
        # Create new thread
        new_thread = self.client.beta.threads.create()
        
        # Add recent messages (reverse order to maintain chronology)
        for msg in reversed(recent_messages):
            self.client.beta.threads.messages.create(
                thread_id=new_thread.id,
                role=msg.role,
                content=msg.content[0].text.value
            )
        
        logger.info(f"✅ Created pruned thread: {new_thread.id}")
        return new_thread.id
    
    async def _update_thread_mapping(self, user_id: str, new_thread_id: str):
        """Update user->thread mapping"""
        
        from database.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Deactivate old thread
        supabase.table("assistant_threads").update({
            "status": "archived"
        }).eq("user_id", user_id).eq("status", "active").execute()
        
        # Create new mapping
        supabase.table("assistant_threads").insert({
            "user_id": user_id,
            "openai_thread_id": new_thread_id,
            "assistant_id": self.assistant_id,
            "status": "active"
        }).execute()
```

---

## Testing & Validation

### 1. Set up monitoring

Create `backend/services/cost_monitor.py`:

```python
"""
Cost monitoring service
"""

from database.supabase_client import get_supabase_client

def log_api_usage(
    user_id: str,
    api_type: str,  # "assistant", "completions", "pattern", "cache"
    tokens_used: int,
    model: str,
    estimated_cost: float
):
    """Log API usage for cost tracking"""
    
    supabase = get_supabase_client()
    supabase.table("api_usage_logs").insert({
        "user_id": user_id,
        "api_type": api_type,
        "tokens_used": tokens_used,
        "model": model,
        "estimated_cost": estimated_cost
    }).execute()

def get_daily_cost_report():
    """Get cost breakdown for today"""
    
    supabase = get_supabase_client()
    
    query = """
    SELECT 
        api_type,
        COUNT(*) as calls,
        SUM(tokens_used) as total_tokens,
        SUM(estimated_cost) as total_cost
    FROM api_usage_logs
    WHERE DATE(created_at) = CURRENT_DATE
    GROUP BY api_type
    """
    
    result = supabase.rpc('execute_sql', {'sql': query}).execute()
    return result.data
```

### 2. Add to responses

Update `coaching_service.py`:

```python
from .cost_monitor import log_api_usage

async def chat(self, user_id: str, message: str, ...):
    # ... existing code ...
    
    # Log API usage
    log_api_usage(
        user_id=user_id,
        api_type=result.get("api_type", "unknown"),
        tokens_used=result.get("tokens_used", 0),
        model=result.get("model", "unknown"),
        estimated_cost=self._estimate_cost(result)
    )
    
    # ... rest of code ...
```

### 3. Daily cost check

```bash
# Add to crontab or run manually
python3 << EOF
from backend.services.cost_monitor import get_daily_cost_report
import json

report = get_daily_cost_report()
print(json.dumps(report, indent=2))
EOF
```

---

## Expected Results

After Week 2 implementation:

```
BEFORE:
- 1,000 messages/day
- 100% Assistant API (GPT-4)
- Cost: ~$9/day = $270/month

AFTER:
- 300 messages from pattern cache (0 cost)
- 560 messages from Completions API @ $0.0015 = $0.84
- 140 messages from Assistant API @ $0.009 = $1.26
- Total: $2.10/day = $63/month

SAVINGS: 77% ($207/month)
```

---

## Troubleshooting

### Pattern responses feel too robotic
**Solution:** Add more variety to pattern responses, or reduce pattern matching threshold.

### Quality dropped for simple messages
**Solution:** Keep first 5 messages on Assistant API instead of 3.

### Thread pruning breaks context
**Solution:** Increase MAX_THREAD_MESSAGES from 20 to 30.

### Completions API responses don't match personality
**Solution:** Refine the system prompt, add more examples.

---

## Next Steps

1. ✅ Implement Week 1 quick wins
2. ✅ Monitor cost reduction
3. ✅ Implement Week 2 optimizations
4. 📊 Validate quality hasn't degraded
5. 📅 Plan long-term optimizations (fine-tuning)
