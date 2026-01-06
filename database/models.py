"""
Pydantic models for data structures.
Used for request/response validation and type hints.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ConversationMemoryBase(BaseModel):
    """Base conversation memory model."""
    message_text: str = Field(..., min_length=1, max_length=10000)
    direction: str = Field(..., pattern=r"^(incoming|outgoing)$")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ConversationMemory(ConversationMemoryBase):
    """Conversation memory with ID and timestamps."""
    id: str
    user_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class CoachStateBase(BaseModel):
    """Base coach state model."""
    last_message_sent_at: Optional[datetime] = None
    last_message_received_at: Optional[datetime] = None
    engagement_score: int = Field(default=50, ge=0, le=100)
    risk_state: str = Field(default="engaged", pattern=r"^(engaged|slipping|churned)$")
    next_message_scheduled_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CoachState(CoachStateBase):
    """Coach state with user ID and timestamps."""
    user_id: str
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserPhoneNumberBase(BaseModel):
    """Base user phone number model."""
    phone_number: str = Field(..., min_length=1, max_length=20)
    is_verified: bool = Field(default=False)


class UserPhoneNumber(UserPhoneNumberBase):
    """User phone number with ID and timestamps."""
    id: str
    user_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Request/Response models for API endpoints

class RegisterPhoneRequest(BaseModel):
    """Request model for registering a phone number."""
    phone_number: str = Field(..., min_length=1, max_length=20)
    is_verified: bool = Field(default=False)
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate phone number format (basic check)."""
        # Remove common separators
        cleaned = v.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        # Should start with + or be digits
        if not (cleaned.startswith('+') or cleaned.isdigit()):
            raise ValueError('Phone number must be in E.164 format or digits only')
        return v


class RegisterPhoneResponse(BaseModel):
    """Response model for phone registration."""
    id: str
    user_id: str
    phone_number: str
    is_verified: bool
    created_at: datetime


class CoachStateResponse(BaseModel):
    """Response model for coach state."""
    user_id: str
    last_message_sent_at: Optional[datetime]
    last_message_received_at: Optional[datetime]
    engagement_score: int
    risk_state: str
    next_message_scheduled_at: Optional[datetime]
    metadata: Dict[str, Any]
    updated_at: datetime


class ConversationMemoryResponse(BaseModel):
    """Response model for conversation memory list."""
    messages: List[ConversationMemory]
    count: int


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None


# Milestone 4: Memory & Personalization Models

class LongTermMemory(BaseModel):
    """Long-term memory model."""
    id: str
    user_id: str
    memory_type: str = Field(..., pattern=r"^(summary|insight|preference|pattern|fact)$")
    content: str
    relevance_score: int = Field(default=50, ge=0, le=100)
    importance_score: int = Field(default=50, ge=0, le=100)
    source_context: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class Commitment(BaseModel):
    """Commitment model."""
    id: str
    user_id: str
    commitment_text: str
    extracted_from_message_id: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str = Field(default="active", pattern=r"^(active|completed|missed|cancelled)$")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    completion_confidence: float = Field(default=0.5, ge=0, le=1)
    reminder_sent: bool = Field(default=False)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class Win(BaseModel):
    """Win/achievement model."""
    id: str
    user_id: str
    win_type: str = Field(..., pattern=r"^(task_completed|commitment_kept|milestone|streak|improvement|custom)$")
    title: str
    description: Optional[str] = None
    related_commitment_id: Optional[str] = None
    related_task_id: Optional[str] = None
    celebration_level: str = Field(default="normal", pattern=r"^(small|normal|big)$")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    
    class Config:
        from_attributes = True


class MoodSignal(BaseModel):
    """Mood/engagement signal model."""
    id: str
    user_id: str
    source_message_id: Optional[str] = None
    mood_type: str = Field(..., pattern=r"^(positive|negative|neutral|motivated|discouraged|stressed|confident|uncertain)$")
    intensity: float = Field(default=0.5, ge=0, le=1)
    engagement_level: int = Field(default=50, ge=0, le=100)
    detected_keywords: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None  # -1 to 1
    metadata: Dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime
    
    class Config:
        from_attributes = True


class MemorySummary(BaseModel):
    """Memory summary model."""
    id: str
    user_id: str
    summary_period_start: datetime
    summary_period_end: datetime
    summary_text: str
    key_topics: List[str] = Field(default_factory=list)
    extracted_commitments: List[str] = Field(default_factory=list)
    extracted_wins: List[str] = Field(default_factory=list)
    mood_trend: Optional[str] = None
    message_count: int = Field(default=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    
    class Config:
        from_attributes = True


class MemoryContext(BaseModel):
    """Complete memory context for AI coach."""
    short_term_messages: List[ConversationMemory] = Field(default_factory=list)
    long_term_memories: List[LongTermMemory] = Field(default_factory=list)
    active_commitments: List[Commitment] = Field(default_factory=list)
    recent_wins: List[Win] = Field(default_factory=list)
    recent_mood_signals: List[MoodSignal] = Field(default_factory=list)
    engagement_context: Optional[Dict[str, Any]] = None


# Milestone 6: App Backend Models

class UserPreferencesBase(BaseModel):
    """Base user preferences model."""
    messaging_frequency: int = Field(default=3, ge=1, le=7)  # times per week
    messaging_style: str = Field(default="balanced", pattern=r"^(firm|balanced|supportive)$")
    response_length: str = Field(default="medium", pattern=r"^(short|medium|long)$")
    quiet_hours_enabled: bool = Field(default=False)
    quiet_hours_start: str = Field(default="22:00", pattern=r"^\d{2}:\d{2}$")  # HH:mm format
    quiet_hours_end: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    quiet_hours_days: List[int] = Field(default_factory=lambda: [0,1,2,3,4,5,6])  # 0=Sunday
    accountability_level: int = Field(default=5, ge=1, le=10)
    goals: List[str] = Field(default_factory=list)
    healthkit_enabled: bool = Field(default=False)
    healthkit_sync_frequency: str = Field(default="daily", pattern=r"^(daily|weekly|manual)$")


class UserPreferences(UserPreferencesBase):
    """User preferences with ID and timestamps."""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UpdatePreferencesRequest(BaseModel):
    """Request model for updating preferences."""
    messaging_frequency: Optional[int] = Field(None, ge=1, le=7)
    messaging_style: Optional[str] = Field(None, pattern=r"^(firm|balanced|supportive)$")
    response_length: Optional[str] = Field(None, pattern=r"^(short|medium|long)$")
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_days: Optional[List[int]] = None
    accountability_level: Optional[int] = Field(None, ge=1, le=10)
    goals: Optional[List[str]] = None
    healthkit_enabled: Optional[bool] = None
    healthkit_sync_frequency: Optional[str] = Field(None, pattern=r"^(daily|weekly|manual)$")


class WeeklySummary(BaseModel):
    """Weekly summary statistics."""
    messages_exchanged: int
    tasks_completed: int
    consistency_score: float  # 0-100
    trend: str = Field(..., pattern=r"^(up|down|neutral)$")
    trend_value: Optional[float] = None


class SleepInsights(BaseModel):
    """Sleep insights."""
    average_hours: Optional[float] = None
    consistency_percentage: Optional[float] = None  # 0-100
    trend: str = Field(default="neutral", pattern=r"^(up|down|neutral)$")
    trend_value: Optional[float] = None


class HabitConsistency(BaseModel):
    """Habit consistency data."""
    overall_score: float  # 0-100
    by_habit: List[Dict[str, Any]] = Field(default_factory=list)


class MoodTrendPoint(BaseModel):
    """Single mood trend data point."""
    date: str  # ISO date string
    value: float  # -1 to 1 (sentiment score)


class MoodTrends(BaseModel):
    """Mood trends data."""
    data_points: List[MoodTrendPoint] = Field(default_factory=list)


class InsightsResponse(BaseModel):
    """Complete insights response."""
    weekly_summary: WeeklySummary
    sleep_insights: SleepInsights
    habit_consistency: HabitConsistency
    mood_trends: MoodTrends


class JournalEntryBase(BaseModel):
    """Base journal entry model."""
    title: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=1)
    mood: Optional[str] = Field(None, pattern=r"^(positive|negative|neutral|motivated|discouraged|stressed|confident|uncertain)$")
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JournalEntry(JournalEntryBase):
    """Journal entry with ID and timestamps."""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CreateJournalEntryRequest(JournalEntryBase):
    """Request model for creating a journal entry."""
    pass


class UpdateJournalEntryRequest(BaseModel):
    """Request model for updating a journal entry."""
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    mood: Optional[str] = Field(None, pattern=r"^(positive|negative|neutral|motivated|discouraged|stressed|confident|uncertain)$")
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class JournalEntriesResponse(BaseModel):
    """Response model for journal entries list."""
    entries: List[JournalEntry]
    count: int
