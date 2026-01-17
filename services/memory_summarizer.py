"""
Memory summarization service.
Creates summaries of conversation periods and extracts key insights.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import logging

from database.supabase_client import get_supabase_client, get_conversation_memory
from services.memory_extractor import analyze_message_for_memory
from services.memory_service import (
    create_long_term_memory,
    create_commitment,
    create_win,
    create_mood_signal
)

logger = logging.getLogger(__name__)


def summarize_conversation_period(
    user_id: str,
    period_start: datetime,
    period_end: datetime,
    force: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Summarize a period of conversation and extract key insights.
    
    This function:
    1. Retrieves messages from the period
    2. Extracts commitments, wins, mood signals
    3. Creates a summary text
    4. Stores summary and extracted insights
    
    Args:
        user_id: User ID
        period_start: Start of period to summarize
        period_end: End of period to summarize
        force: Force creation even if summary already exists
        
    Returns:
        Created summary record
    """
    client = get_supabase_client()
    
    # Check if summary already exists (unless forcing)
    if not force:
        existing = client.table("memory_summaries")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("summary_period_start", period_start.isoformat())\
            .eq("summary_period_end", period_end.isoformat())\
            .limit(1)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            logger.info(f"Summary already exists for period {period_start} to {period_end}")
            return existing.data[0]
    
    # Get all messages in this period
    all_messages = get_conversation_memory(user_id, limit=1000)  # Get more for analysis
    
    # Filter messages by period
    period_messages = [
        msg for msg in all_messages
        if period_start <= datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00')) <= period_end
    ]
    
    if not period_messages:
        logger.info(f"No messages in period {period_start} to {period_end}")
        return None
    
    # Extract insights from messages
    extracted_commitments = []
    extracted_wins = []
    mood_signals = []
    key_topics = []
    
    for msg in period_messages:
        if msg['direction'] == 'incoming':
            analysis = analyze_message_for_memory(
                user_id,
                msg['message_text'],
                msg['id'],
                msg['direction']
            )
            
            # Process commitments
            for comm in analysis['commitments']:
                extracted_commitments.append(comm['commitment_text'])
                # Create commitment record if confidence is high enough
                if comm.get('confidence', 0) > 0.6:
                    try:
                        create_commitment(
                            user_id=user_id,
                            commitment_text=comm['commitment_text'],
                            extracted_from_message_id=msg['id'],
                            priority=comm.get('priority', 'medium'),
                            completion_confidence=comm.get('confidence', 0.6)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create commitment: {e}")
            
            # Process wins
            for win in analysis['wins']:
                extracted_wins.append(win['title'])
                try:
                    create_win(
                        user_id=user_id,
                        win_type=win['win_type'],
                        title=win['title'],
                        description=win.get('description'),
                        celebration_level=win.get('celebration_level', 'normal')
                    )
                except Exception as e:
                    logger.warning(f"Failed to create win: {e}")
            
            # Process mood signal
            if analysis['mood_signal']:
                mood_signals.append(analysis['mood_signal'])
                try:
                    create_mood_signal(
                        user_id=user_id,
                        mood_type=analysis['mood_signal']['mood_type'],
                        intensity=analysis['mood_signal']['intensity'],
                        engagement_level=analysis['mood_signal']['engagement_level'],
                        source_message_id=msg['id'],
                        detected_keywords=analysis['mood_signal'].get('detected_keywords', []),
                        sentiment_score=analysis['mood_signal'].get('sentiment_score')
                    )
                except Exception as e:
                    logger.warning(f"Failed to create mood signal: {e}")
            
            # Extract topics (simple keyword extraction - can be enhanced)
            words = msg['message_text'].lower().split()
            # Add common topic words
            topic_words = [w for w in words if len(w) > 4 and w not in ['that', 'this', 'with', 'from', 'they', 'them']]
            key_topics.extend(topic_words[:3])  # Limit per message
    
    # Determine overall mood trend
    mood_trend = "neutral"
    if mood_signals:
        positive_count = sum(1 for m in mood_signals if m['sentiment_score'] and m['sentiment_score'] > 0.2)
        negative_count = sum(1 for m in mood_signals if m['sentiment_score'] and m['sentiment_score'] < -0.2)
        
        if positive_count > negative_count * 1.5:
            mood_trend = "positive"
        elif negative_count > positive_count * 1.5:
            mood_trend = "negative"
        elif positive_count > 0:
            mood_trend = "mostly_positive"
        elif negative_count > 0:
            mood_trend = "mostly_negative"
    
    # Create summary text
    summary_text = _generate_summary_text(
        message_count=len(period_messages),
        commitments=extracted_commitments,
        wins=extracted_wins,
        mood_trend=mood_trend,
        key_topics=list(set(key_topics))[:10]  # Top 10 unique topics
    )
    
    # Store summary
    response = client.table("memory_summaries")\
        .insert({
            "user_id": user_id,
            "summary_period_start": period_start.isoformat(),
            "summary_period_end": period_end.isoformat(),
            "summary_text": summary_text,
            "key_topics": list(set(key_topics))[:10],
            "extracted_commitments": extracted_commitments[:20],  # Limit
            "extracted_wins": extracted_wins[:20],  # Limit
            "mood_trend": mood_trend,
            "message_count": len(period_messages)
        })\
        .execute()
    
    if response.data and len(response.data) > 0:
        summary = response.data[0]
        
        # Create long-term memory entry from summary
        try:
            create_long_term_memory(
                user_id=user_id,
                memory_type="summary",
                content=summary_text,
                relevance_score=70,  # Summaries are fairly relevant
                importance_score=60,  # Moderately important
                source_context=f"Summary of period {period_start.date()} to {period_end.date()}",
                tags=["summary", f"period_{period_start.strftime('%Y_%m')}"],
                metadata={
                    "summary_id": summary['id'],
                    "message_count": len(period_messages),
                    "mood_trend": mood_trend
                }
            )
        except Exception as e:
            logger.warning(f"Failed to create long-term memory from summary: {e}")
        
        return summary
    
    return None


def _generate_summary_text(
    message_count: int,
    commitments: List[str],
    wins: List[str],
    mood_trend: str,
    key_topics: List[str]
) -> str:
    """
    Generate summary text from extracted information.
    
    Args:
        message_count: Number of messages in period
        commitments: List of commitment texts
        wins: List of win texts
        mood_trend: Overall mood trend
        key_topics: List of key topics
        
    Returns:
        Summary text
    """
    parts = []
    
    parts.append(f"During this period, there were {message_count} messages exchanged.")
    
    if mood_trend != "neutral":
        mood_desc = {
            "positive": "The user's mood was generally positive",
            "negative": "The user's mood was generally negative",
            "mostly_positive": "The user's mood was mostly positive",
            "mostly_negative": "The user's mood was mostly negative"
        }
        parts.append(mood_desc.get(mood_trend, ""))
    
    if commitments:
        parts.append(f"The user made {len(commitments)} commitment(s), including: {', '.join(commitments[:3])}.")
    
    if wins:
        parts.append(f"The user achieved {len(wins)} win(s), such as: {', '.join(wins[:3])}.")
    
    if key_topics:
        parts.append(f"Key topics discussed included: {', '.join(key_topics[:5])}.")
    
    return " ".join(parts)


def auto_summarize_recent_periods(user_id: str, days_back: int = 7) -> List[Dict[str, Any]]:
    """
    Automatically summarize recent conversation periods.
    
    Summarizes the last N days into daily or weekly summaries.
    
    Args:
        user_id: User ID
        days_back: Number of days to summarize
        
    Returns:
        List of created summaries
    """
    now = datetime.now(timezone.utc)
    summaries = []
    
    # Summarize daily periods (last N days)
    for i in range(days_back):
        period_end = now - timedelta(days=i)
        period_start = period_end - timedelta(days=1)
        
        try:
            summary = summarize_conversation_period(user_id, period_start, period_end)
            if summary:
                summaries.append(summary)
        except Exception as e:
            logger.error(f"Failed to summarize period {period_start} to {period_end}: {e}")
    
    return summaries


def cleanup_expired_memories(user_id: Optional[str] = None) -> int:
    """
    Clean up expired long-term memories.
    
    Args:
        user_id: Optional user ID to clean for specific user, or None for all users
        
    Returns:
        Number of deleted memories
    """
    client = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()
    
    query = client.table("long_term_memory")\
        .delete()\
        .not_.is_("expires_at", "null")\
        .lt("expires_at", now)
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    response = query.execute()
    
    # Count deleted (Supabase doesn't return count, so we'll estimate)
    deleted_count = 1 if response.data else 0  # Placeholder
    
    logger.info(f"Cleaned up expired memories for user {user_id or 'all'}")
    return deleted_count


def archive_old_conversation_memory(user_id: str, days_to_keep: int = 30) -> int:
    """
    Archive old conversation memory by summarizing and deleting old messages.
    
    This implements the storage rule: keep last N days of raw messages,
    summarize older messages into long-term memory.
    
    Args:
        user_id: User ID
        days_to_keep: Number of days of raw messages to keep
        
    Returns:
        Number of messages archived/summarized
    """
    client = get_supabase_client()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()
    
    # Get old messages to archive
    old_messages = client.table("conversation_memory")\
        .select("*")\
        .eq("user_id", user_id)\
        .lt("created_at", cutoff_date)\
        .order("created_at", desc=False)\
        .limit(1000)\
        .execute()
    
    if not old_messages.data:
        return 0
    
    # Group messages by week for summarization
    message_count = len(old_messages.data)
    
    # Summarize each week's messages
    weeks = {}
    for msg in old_messages.data:
        msg_date = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00'))
        week_key = msg_date.strftime('%Y-W%W')
        if week_key not in weeks:
            weeks[week_key] = []
        weeks[week_key].append(msg)
    
    summaries_created = 0
    for week_key, week_messages in weeks.items():
        if week_messages:
            period_start = datetime.fromisoformat(week_messages[0]['created_at'].replace('Z', '+00:00'))
            period_end = datetime.fromisoformat(week_messages[-1]['created_at'].replace('Z', '+00:00'))
            
            try:
                summary = summarize_conversation_period(user_id, period_start, period_end, force=True)
                if summary:
                    summaries_created += 1
            except Exception as e:
                logger.error(f"Failed to summarize week {week_key}: {e}")
    
    # Delete old messages (optional - could keep them if desired)
    # For now, we'll keep them but they're summarized
    # Uncomment to actually delete:
    # client.table("conversation_memory")\
    #     .delete()\
    #     .eq("user_id", user_id)\
    #     .lt("created_at", cutoff_date)\
    #     .execute()
    
    logger.info(f"Archived {message_count} old messages into {summaries_created} summaries for user {user_id}")
    return message_count





