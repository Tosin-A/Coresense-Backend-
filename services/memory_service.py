"""
Memory service for retrieving and managing user memory context.
Handles short-term vs long-term memory, commitments, wins, and mood signals.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import logging

from database.supabase_client import get_supabase_client, get_conversation_memory
from database.models import (
    MemoryContext, ConversationMemory, LongTermMemory, Commitment, Win, MoodSignal
)

logger = logging.getLogger(__name__)


def get_memory_context(user_id: str, short_term_limit: int = 20) -> MemoryContext:
    """
    Get complete memory context for AI coach.
    
    Combines:
    - Short-term: Recent conversation messages
    - Long-term: Relevant long-term memories
    - Active commitments
    - Recent wins (for motivation)
    - Recent mood signals
    
    Args:
        user_id: User ID
        short_term_limit: Number of recent messages to include
        
    Returns:
        MemoryContext with all relevant context
    """
    client = get_supabase_client()
    
    # Short-term memory: recent conversation
    short_term_messages = get_conversation_memory(user_id, limit=short_term_limit)
    
    # Long-term memory: relevant memories (high relevance/importance, not expired)
    long_term_memories = _get_relevant_long_term_memories(client, user_id)
    
    # Active commitments
    active_commitments = _get_active_commitments(client, user_id)
    
    # Recent wins (last 7 days)
    recent_wins = _get_recent_wins(client, user_id, days=7)
    
    # Recent mood signals (last 14 days)
    recent_mood_signals = _get_recent_mood_signals(client, user_id, days=14)
    
    # Engagement context from coach state
    engagement_context = _get_engagement_context(client, user_id)
    
    return MemoryContext(
        short_term_messages=[ConversationMemory(**msg) for msg in short_term_messages],
        long_term_memories=[LongTermMemory(**mem) for mem in long_term_memories],
        active_commitments=[Commitment(**comm) for comm in active_commitments],
        recent_wins=[Win(**win) for win in recent_wins],
        recent_mood_signals=[MoodSignal(**mood) for mood in recent_mood_signals],
        engagement_context=engagement_context
    )


def _get_relevant_long_term_memories(client, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get relevant long-term memories (sorted by relevance and importance, not expired)."""
    now = datetime.now(timezone.utc)
    
    response = client.table("long_term_memory")\
        .select("*")\
        .eq("user_id", user_id)\
        .or_("expires_at.is.null,expires_at.gt." + now.isoformat())\
        .order("relevance_score", desc=True)\
        .order("importance_score", desc=True)\
        .limit(limit)\
        .execute()
    
    # Update last_accessed_at for retrieved memories
    if response.data:
        memory_ids = [mem['id'] for mem in response.data]
        client.table("long_term_memory")\
            .update({"last_accessed_at": now.isoformat()})\
            .in_("id", memory_ids)\
            .execute()
    
    return response.data if response.data else []


def _get_active_commitments(client, user_id: str) -> List[Dict[str, Any]]:
    """Get active commitments (not completed, missed, or cancelled)."""
    response = client.table("commitments")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("status", "active")\
        .order("due_date", desc=False)\
        .order("priority", desc=True)\
        .limit(20)\
        .execute()
    
    return response.data if response.data else []


def _get_recent_wins(client, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """Get recent wins for motivation."""
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    response = client.table("wins")\
        .select("*")\
        .eq("user_id", user_id)\
        .gte("created_at", cutoff_date)\
        .order("created_at", desc=True)\
        .limit(10)\
        .execute()
    
    return response.data if response.data else []


def _get_recent_mood_signals(client, user_id: str, days: int = 14) -> List[Dict[str, Any]]:
    """Get recent mood signals for context."""
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    response = client.table("mood_signals")\
        .select("*")\
        .eq("user_id", user_id)\
        .gte("detected_at", cutoff_date)\
        .order("detected_at", desc=True)\
        .limit(20)\
        .execute()
    
    return response.data if response.data else []


def _get_engagement_context(client, user_id: str) -> Optional[Dict[str, Any]]:
    """Get engagement context from coach state."""
    from database.supabase_client import get_coach_state
    
    coach_state = get_coach_state(user_id)
    if not coach_state:
        return None
    
    return {
        "engagement_score": coach_state.get("engagement_score", 50),
        "risk_state": coach_state.get("risk_state", "engaged"),
        "last_message_sent_at": coach_state.get("last_message_sent_at"),
        "last_message_received_at": coach_state.get("last_message_received_at"),
    }


def create_long_term_memory(
    user_id: str,
    memory_type: str,
    content: str,
    relevance_score: int = 50,
    importance_score: int = 50,
    source_context: Optional[str] = None,
    tags: Optional[List[str]] = None,
    expires_at: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a long-term memory entry.
    
    Args:
        user_id: User ID
        memory_type: Type of memory (summary, insight, preference, pattern, fact)
        content: Memory content
        relevance_score: Relevance score (0-100)
        importance_score: Importance score (0-100)
        source_context: Context where this memory came from
        tags: Tags for categorization
        expires_at: Optional expiration date
        metadata: Additional metadata
        
    Returns:
        Created memory record
    """
    client = get_supabase_client()
    
    response = client.table("long_term_memory")\
        .insert({
            "user_id": user_id,
            "memory_type": memory_type,
            "content": content,
            "relevance_score": relevance_score,
            "importance_score": importance_score,
            "source_context": source_context,
            "tags": tags or [],
            "expires_at": expires_at.isoformat() if expires_at else None,
            "metadata": metadata or {},
            "last_accessed_at": datetime.now(timezone.utc).isoformat()
        })\
        .execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    raise Exception("Failed to create long-term memory")


def create_commitment(
    user_id: str,
    commitment_text: str,
    extracted_from_message_id: Optional[str] = None,
    due_date: Optional[datetime] = None,
    priority: str = "medium",
    completion_confidence: float = 0.5,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a commitment record.
    
    Args:
        user_id: User ID
        commitment_text: Text of the commitment
        extracted_from_message_id: Message ID where this was extracted from
        due_date: Optional due date
        priority: Priority level (low, medium, high)
        completion_confidence: Confidence in completion (0-1)
        metadata: Additional metadata
        
    Returns:
        Created commitment record
    """
    client = get_supabase_client()
    
    response = client.table("commitments")\
        .insert({
            "user_id": user_id,
            "commitment_text": commitment_text,
            "extracted_from_message_id": extracted_from_message_id,
            "due_date": due_date.isoformat() if due_date else None,
            "priority": priority,
            "completion_confidence": completion_confidence,
            "metadata": metadata or {}
        })\
        .execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    raise Exception("Failed to create commitment")


def create_win(
    user_id: str,
    win_type: str,
    title: str,
    description: Optional[str] = None,
    related_commitment_id: Optional[str] = None,
    related_task_id: Optional[str] = None,
    celebration_level: str = "normal",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a win/achievement record.
    
    Args:
        user_id: User ID
        win_type: Type of win (task_completed, commitment_kept, milestone, streak, improvement, custom)
        title: Win title
        description: Win description
        related_commitment_id: Related commitment ID if applicable
        related_task_id: Related task ID if applicable
        celebration_level: Celebration level (small, normal, big)
        metadata: Additional metadata
        
    Returns:
        Created win record
    """
    client = get_supabase_client()
    
    response = client.table("wins")\
        .insert({
            "user_id": user_id,
            "win_type": win_type,
            "title": title,
            "description": description,
            "related_commitment_id": related_commitment_id,
            "related_task_id": related_task_id,
            "celebration_level": celebration_level,
            "metadata": metadata or {}
        })\
        .execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    raise Exception("Failed to create win")


def create_mood_signal(
    user_id: str,
    mood_type: str,
    intensity: float = 0.5,
    engagement_level: int = 50,
    source_message_id: Optional[str] = None,
    detected_keywords: Optional[List[str]] = None,
    sentiment_score: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a mood/engagement signal.
    
    Args:
        user_id: User ID
        mood_type: Type of mood (positive, negative, neutral, motivated, discouraged, stressed, confident, uncertain)
        intensity: Mood intensity (0-1)
        engagement_level: Engagement level (0-100)
        source_message_id: Message ID where this was detected
        detected_keywords: Keywords that triggered this mood detection
        sentiment_score: Sentiment score (-1 to 1)
        metadata: Additional metadata
        
    Returns:
        Created mood signal record
    """
    client = get_supabase_client()
    
    response = client.table("mood_signals")\
        .insert({
            "user_id": user_id,
            "mood_type": mood_type,
            "intensity": intensity,
            "engagement_level": engagement_level,
            "source_message_id": source_message_id,
            "detected_keywords": detected_keywords or [],
            "sentiment_score": sentiment_score,
            "metadata": metadata or {}
        })\
        .execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    raise Exception("Failed to create mood signal")


def update_commitment_status(
    commitment_id: str,
    status: str,
    completed_at: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Update commitment status (e.g., mark as completed).
    
    Args:
        commitment_id: Commitment ID
        status: New status (active, completed, missed, cancelled)
        completed_at: Completion timestamp if applicable
        
    Returns:
        Updated commitment record
    """
    client = get_supabase_client()
    
    updates = {"status": status}
    if completed_at:
        updates["completed_at"] = completed_at.isoformat()
    
    response = client.table("commitments")\
        .update(updates)\
        .eq("id", commitment_id)\
        .execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    raise Exception("Failed to update commitment status")


def get_missed_commitments(user_id: str) -> List[Dict[str, Any]]:
    """
    Get commitments that are past due and not completed.
    
    Args:
        user_id: User ID
        
    Returns:
        List of missed commitments
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc)
    
    response = client.table("commitments")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("status", "active")\
        .lt("due_date", now.isoformat())\
        .execute()
    
    return response.data if response.data else []





