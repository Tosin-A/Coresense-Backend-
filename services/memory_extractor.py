"""
Memory extraction service.
Extracts wins, mood signals, and insights from messages.
Uses simple pattern matching and keyword detection (can be enhanced with NLP later).
"""

from typing import List, Dict, Any, Optional, Tuple
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Keyword patterns for mood detection
POSITIVE_MOOD_KEYWORDS = [
    'great', 'good', 'excited', 'happy', 'awesome', 'amazing', 'love', 'wonderful',
    'fantastic', 'proud', 'confident', 'motivated', 'ready', 'yes', 'yeah', 'sure'
]

NEGATIVE_MOOD_KEYWORDS = [
    'bad', 'terrible', 'awful', 'hate', 'sad', 'frustrated', 'stressed', 'anxious',
    'worried', 'tired', 'exhausted', 'stuck', 'hard', 'difficult', 'no', 'cant', "can't"
]

MOTIVATED_KEYWORDS = [
    'motivated', 'ready', 'excited', 'lets do', "let's do", 'lets go', "let's go",
    'im ready', "i'm ready", 'bring it', 'lets start', "let's start"
]

DISCOURAGED_KEYWORDS = [
    'give up', 'quit', 'cant do', "can't do", 'too hard', 'impossible', 'never',
    'hopeless', 'stuck', 'lost', 'dont know', "don't know"
]

STRESSED_KEYWORDS = [
    'stressed', 'overwhelmed', 'anxious', 'worried', 'pressure', 'deadline',
    'too much', 'so much', 'busy', 'hectic'
]

CONFIDENT_KEYWORDS = [
    'confident', 'sure', 'definitely', 'absolutely', 'no problem', 'easy',
    'got this', 'can do', 'will do'
]

UNCERTAIN_KEYWORDS = [
    'maybe', 'not sure', 'dont know', "don't know", 'unsure', 'think so',
    'might', 'possibly', 'perhaps'
]

# Win detection patterns
WIN_KEYWORDS = [
    r'\b(done|finished|completed|accomplished|achieved|did it|got it done)\b',
    r'\b(proud|excited|happy about|celebrate|success|win|achievement)\b',
    r'\b(streak|days in a row|consistent|kept going)\b',
]


def extract_mood_signal(message_text: str, message_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Extract mood and engagement signal from a message.
    
    Args:
        message_text: Message text to analyze
        message_id: Optional message ID for reference
        
    Returns:
        Mood signal dictionary with:
        - mood_type: Detected mood type
        - intensity: Intensity score (0-1)
        - engagement_level: Engagement level (0-100)
        - detected_keywords: Keywords that triggered detection
        - sentiment_score: Overall sentiment (-1 to 1)
    """
    message_lower = message_text.lower()
    detected_keywords = []
    mood_type = "neutral"
    intensity = 0.5
    sentiment_score = 0.0
    
    # Check for positive mood
    positive_matches = [word for word in POSITIVE_MOOD_KEYWORDS if word in message_lower]
    if positive_matches:
        mood_type = "positive"
        intensity = min(0.5 + (len(positive_matches) * 0.1), 1.0)
        sentiment_score = 0.5 + (len(positive_matches) * 0.1)
        detected_keywords.extend(positive_matches)
    
    # Check for negative mood
    negative_matches = [word for word in NEGATIVE_MOOD_KEYWORDS if word in message_lower]
    if negative_matches:
        if mood_type == "positive":
            # Mixed signals - use the stronger one
            if len(negative_matches) > len(positive_matches):
                mood_type = "negative"
                intensity = min(0.5 + (len(negative_matches) * 0.1), 1.0)
                sentiment_score = -0.5 - (len(negative_matches) * 0.1)
                detected_keywords = negative_matches
        else:
            mood_type = "negative"
            intensity = min(0.5 + (len(negative_matches) * 0.1), 1.0)
            sentiment_score = -0.5 - (len(negative_matches) * 0.1)
            detected_keywords.extend(negative_matches)
    
    # Check for specific mood types (override if detected)
    if any(word in message_lower for word in MOTIVATED_KEYWORDS):
        mood_type = "motivated"
        intensity = 0.7
        sentiment_score = 0.6
        detected_keywords.extend([w for w in MOTIVATED_KEYWORDS if w in message_lower])
    
    if any(word in message_lower for word in DISCOURAGED_KEYWORDS):
        mood_type = "discouraged"
        intensity = 0.8
        sentiment_score = -0.7
        detected_keywords.extend([w for w in DISCOURAGED_KEYWORDS if w in message_lower])
    
    if any(word in message_lower for word in STRESSED_KEYWORDS):
        mood_type = "stressed"
        intensity = 0.75
        sentiment_score = -0.5
        detected_keywords.extend([w for w in STRESSED_KEYWORDS if w in message_lower])
    
    if any(word in message_lower for word in CONFIDENT_KEYWORDS):
        mood_type = "confident"
        intensity = 0.7
        sentiment_score = 0.7
        detected_keywords.extend([w for w in CONFIDENT_KEYWORDS if w in message_lower])
    
    if any(word in message_lower for word in UNCERTAIN_KEYWORDS):
        mood_type = "uncertain"
        intensity = 0.6
        sentiment_score = -0.2
        detected_keywords.extend([w for w in UNCERTAIN_KEYWORDS if w in message_lower])
    
    # Calculate engagement level based on message characteristics
    engagement_level = 50  # Base level
    
    # Longer messages = higher engagement
    word_count = len(message_text.split())
    if word_count > 20:
        engagement_level += 10
    elif word_count < 5:
        engagement_level -= 10
    
    # Questions = engagement
    if '?' in message_text:
        engagement_level += 5
    
    # Exclamation = engagement
    if '!' in message_text:
        engagement_level += 5
    
    # Adjust based on sentiment
    if sentiment_score > 0.3:
        engagement_level += 10
    elif sentiment_score < -0.3:
        engagement_level -= 10
    
    engagement_level = max(0, min(100, engagement_level))
    
    # Only return if we detected something meaningful
    if mood_type != "neutral" or len(detected_keywords) > 0:
        return {
            "mood_type": mood_type,
            "intensity": min(1.0, max(0.0, intensity)),
            "engagement_level": engagement_level,
            "detected_keywords": list(set(detected_keywords)),
            "sentiment_score": max(-1.0, min(1.0, sentiment_score)),
            "source_message_id": message_id
        }
    
    return None


def extract_wins(message_text: str, message_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract wins/achievements from a message.
    
    Args:
        message_text: Message text to analyze
        message_id: Optional message ID for reference
        
    Returns:
        List of win dictionaries
    """
    wins = []
    message_lower = message_text.lower()
    
    # Check for win indicators
    has_win_language = any(
        re.search(pattern, message_lower, re.IGNORECASE)
        for pattern in WIN_KEYWORDS
    )
    
    if not has_win_language:
        return wins
    
    # Try to extract what was accomplished
    sentences = re.split(r'[.!?]+', message_text)
    
    for sentence in sentences:
        sentence_lower = sentence.lower().strip()
        if not sentence_lower:
            continue
        
        # Check if this sentence indicates a win
        has_win_keyword = any(
            re.search(pattern, sentence_lower, re.IGNORECASE)
            for pattern in WIN_KEYWORDS
        )
        
        if has_win_keyword:
            # Determine win type
            win_type = "custom"
            if 'streak' in sentence_lower or 'days in a row' in sentence_lower:
                win_type = "streak"
            elif any(word in sentence_lower for word in ['task', 'assignment', 'project']):
                win_type = "task_completed"
            elif 'milestone' in sentence_lower:
                win_type = "milestone"
            
            # Determine celebration level
            celebration_level = "normal"
            if any(word in sentence_lower for word in ['amazing', 'awesome', 'incredible', 'huge']):
                celebration_level = "big"
            elif any(word in sentence_lower for word in ['small', 'little', 'minor']):
                celebration_level = "small"
            
            wins.append({
                "win_type": win_type,
                "title": sentence.strip()[:100],  # Limit title length
                "description": sentence.strip(),
                "celebration_level": celebration_level,
                "extracted_from_message_id": message_id
            })
    
    # If no specific sentences, check if whole message is a win
    if not wins and len(message_text.split()) < 30:
        # Short celebratory messages might be full wins
        if any(re.search(pattern, message_lower, re.IGNORECASE) for pattern in WIN_KEYWORDS):
            wins.append({
                "win_type": "custom",
                "title": message_text.strip()[:100],
                "description": message_text.strip(),
                "celebration_level": "normal",
                "extracted_from_message_id": message_id
            })
    
    return wins


def analyze_message_for_memory(
    user_id: str,
    message_text: str,
    message_id: Optional[str] = None,
    direction: str = "incoming"
) -> Dict[str, Any]:
    """
    Analyze a message and extract all memory-related information.
    
    Args:
        user_id: User ID
        message_text: Message text
        message_id: Message ID
        direction: Message direction (incoming/outgoing)
        
    Returns:
        Dictionary with extracted:
        - mood_signal: Mood signal dict (if detected)
        - wins: List of wins
    """
    if direction != "incoming":
        # Only analyze incoming messages from users
        return {"mood_signal": None, "wins": []}
    
    mood_signal = extract_mood_signal(message_text, message_id)
    wins = extract_wins(message_text, message_id)

    return {
        "mood_signal": mood_signal,
        "wins": wins
    }





