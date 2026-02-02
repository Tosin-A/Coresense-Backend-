"""
Context Service - Extracted from context_injector
Minimal context injection for Assistant-Native architecture
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


@dataclass
class TodoItem:
    """Todo item for context"""
    title: str
    priority: str
    due_date: Optional[str]
    created_by: str  # 'user' or 'coach'
    coach_reasoning: Optional[str] = None


@dataclass
class EssentialContext:
    """Minimal context needed for thread initialization"""
    user_name: str
    current_streak: int
    longest_streak: int
    active_commitments: List[str]
    pending_todos: List[TodoItem]  # User's pending tasks
    user_id: str
    context_type: str  # 'initialization' | 'update' | 'minimal'


class ContextService:
    """
    Minimal context injection service - provides only essential context
    
    Features:
    - Minimal context for thread initialization
    - Context change detection
    - Fallback mechanisms
    - No expensive comprehensive context fetching
    """
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def get_essential_context(self, user_id: str, context_type: str = "minimal") -> EssentialContext:
        """Get essential context only - this replaces get_comprehensive_context()"""
        try:
            if context_type == "initialization":
                return await self._get_initialization_context(user_id)
            elif context_type == "update":
                return await self._get_update_context(user_id)
            else:
                return await self._get_minimal_context(user_id)
            
        except Exception as e:
            logger.error(f"Error getting essential context for {user_id}: {e}")
            return self._get_fallback_context(user_id)
    
    async def should_inject_context(self, user_id: str) -> bool:
        """Determine if context should be injected (e.g., thread creation or significant changes)"""
        try:
            # Check if thread exists
            thread_response = self.supabase.table("assistant_threads").select(
                "id, created_at, last_context_injection"
            ).eq("user_id", user_id).eq("status", "active").execute()
            
            if not thread_response.data:
                # No thread exists - need to inject context
                return True
            
            # Check if context was recently injected
            thread = thread_response.data[0]
            last_injection = thread.get("last_context_injection")
            
            if not last_injection:
                # No context injection record - inject
                return True
            
            # Check if user data has changed significantly
            return await self._has_significant_data_change(user_id, last_injection)
            
        except Exception as e:
            logger.error(f"Error checking context injection need: {e}")
            return True  # Default to injecting context if we can't check
    
    async def inject_context_to_thread(self, user_id: str, thread_id: str):
        """Inject context to existing thread"""
        try:
            if not self.should_inject_context(user_id):
                return
            
            # Get essential context
            context = await self.get_essential_context(user_id, "initialization")
            
            # Format as message for Assistant
            context_message = self._build_context_message(context)
            
            # Add as system message to thread (handled by thread management)
            # This would be called by thread management service
            
            # Update injection timestamp
            await self._update_context_injection_time(user_id)
            
            logger.info(f"🎯 Injected context for user {user_id} to thread {thread_id}")
            
        except Exception as e:
            logger.error(f"Error injecting context: {e}")
            # Don't fail thread creation if context injection fails
    
    def format_for_assistant(self, context: EssentialContext) -> str:
        """Format context as message for Assistant"""
        commitments_text = ", ".join(context.active_commitments) if context.active_commitments else "None"

        # Format todos for the assistant
        if context.pending_todos:
            todos_lines = []
            for todo in context.pending_todos:
                due_info = f" (due: {todo.due_date})" if todo.due_date else ""
                creator = "coach-assigned" if todo.created_by == "coach" else "self-set"
                todos_lines.append(f"  - {todo.title} [{todo.priority}]{due_info} ({creator})")
            todos_text = "\n".join(todos_lines)
        else:
            todos_text = "  None"

        return f"""USER CONTEXT UPDATE:

Name: {context.user_name}
Current Streak: {context.current_streak} days
Longest Streak: {context.longest_streak} days
Active Commitments: {commitments_text}

Pending Tasks (nudge them about these):
{todos_text}

Context Type: {context.context_type}"""
    
    # Private helper methods
    
    async def _get_initialization_context(self, user_id: str) -> EssentialContext:
        """Get comprehensive context for thread initialization"""
        # Get user name
        user_name = await self._get_user_name(user_id)

        # Get streak data
        current_streak, longest_streak = await self._get_streak_data(user_id)

        # Get active commitments
        active_commitments = await self._get_active_commitments(user_id)

        # Get pending todos - tasks the coach can reference and nudge about
        pending_todos = await self._get_pending_todos(user_id)

        return EssentialContext(
            user_name=user_name,
            current_streak=current_streak,
            longest_streak=longest_streak,
            active_commitments=active_commitments,
            pending_todos=pending_todos,
            user_id=user_id,
            context_type="initialization"
        )
    
    async def _get_update_context(self, user_id: str) -> EssentialContext:
        """Get context for significant updates"""
        # Similar to initialization but may be more selective
        return await self._get_initialization_context(user_id)
    
    async def _get_minimal_context(self, user_id: str) -> EssentialContext:
        """Get minimal context - just essentials"""
        user_name = await self._get_user_name(user_id)
        current_streak, _ = await self._get_streak_data(user_id)
        pending_todos = await self._get_pending_todos(user_id)

        return EssentialContext(
            user_name=user_name,
            current_streak=current_streak,
            longest_streak=0,
            active_commitments=[],
            pending_todos=pending_todos,
            user_id=user_id,
            context_type="minimal"
        )
    
    async def _get_user_name(self, user_id: str) -> str:
        """Get user's name"""
        try:
            response = self.supabase.table("users").select("name").eq("id", user_id).execute()
            if response.data:
                return response.data[0].get("name", "User")
            return "User"
        except Exception as e:
            logger.error(f"Error getting user name: {e}")
            # If the name column doesn't exist, try to get other identifying info
            try:
                response = self.supabase.table("users").select("id").eq("id", user_id).execute()
                if response.data:
                    return "User"  # Default fallback
            except:
                pass
            return "User"
    
    async def _get_streak_data(self, user_id: str) -> tuple[int, int]:
        """Get current and longest streak"""
        try:
            response = self.supabase.table("user_streaks").select(
                "current_streak, longest_streak"
            ).eq("user_id", user_id).execute()
            
            if response.data:
                return (
                    response.data[0].get("current_streak", 0),
                    response.data[0].get("longest_streak", 0)
                )
            return 0, 0
        except Exception as e:
            logger.error(f"Error getting streak data: {e}")
            return 0, 0
    
    async def _get_active_commitments(self, user_id: str) -> List[str]:
        """Get active commitments"""
        try:
            response = self.supabase.table("commitments").select(
                "commitment_text"
            ).eq("user_id", user_id).eq("status", "active").limit(3).execute()

            if response.data:
                return [c["commitment_text"] for c in response.data]
            return []
        except Exception as e:
            logger.error(f"Error getting active commitments: {e}")
            return []

    async def _get_pending_todos(self, user_id: str) -> List[TodoItem]:
        """Get pending todos for user - these are tasks the coach can nudge about"""
        try:
            response = self.supabase.table("shared_todos").select(
                "title, priority, due_date, created_by, coach_reasoning"
            ).eq("user_id", user_id).in_("status", ["pending", "in_progress"]).limit(5).execute()

            if response.data:
                return [
                    TodoItem(
                        title=t["title"],
                        priority=t.get("priority", "medium"),
                        due_date=t.get("due_date"),
                        created_by=t.get("created_by", "user"),
                        coach_reasoning=t.get("coach_reasoning")
                    )
                    for t in response.data
                ]
            return []
        except Exception as e:
            logger.error(f"Error getting pending todos: {e}")
            return []
    
    async def _has_significant_data_change(self, user_id: str, last_injection: str) -> bool:
        """Check if user data has changed significantly since last context injection"""
        try:
            # Check for new commitments
            commitments_response = self.supabase.table("commitments").select(
                "id, created_at"
            ).eq("user_id", user_id).gte("created_at", last_injection).execute()
            
            if commitments_response.data:
                return True
            
            # Check for streak changes
            streak_response = self.supabase.table("user_streaks").select(
                "updated_at"
            ).eq("user_id", user_id).gte("updated_at", last_injection).execute()
            
            if streak_response.data:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking data changes: {e}")
            return False
    
    def _build_context_message(self, context: EssentialContext) -> str:
        """Build context message for Assistant"""
        return self.format_for_assistant(context)
    
    async def _update_context_injection_time(self, user_id: str):
        """Update the last context injection timestamp"""
        try:
            self.supabase.table("assistant_threads").update({
                "last_context_injection": datetime.now().isoformat()
            }).eq("user_id", user_id).eq("status", "active").execute()
        except Exception as e:
            logger.error(f"Error updating context injection time: {e}")
    
    def _get_fallback_context(self, user_id: str) -> EssentialContext:
        """Get minimal fallback context"""
        return EssentialContext(
            user_name="User",
            current_streak=0,
            longest_streak=0,
            active_commitments=[],
            pending_todos=[],
            user_id=user_id,
            context_type="fallback"
        )


# Global context service instance
context_service = ContextService()