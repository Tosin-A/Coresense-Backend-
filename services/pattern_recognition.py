"""
Pattern Recognition Service
Analyzes user behavior patterns and generates actionable insights
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import statistics

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class PatternType(Enum):
    USAGE_PATTERN = "usage_pattern"
    RESPONSE_PATTERN = "response_pattern"
    TIME_PATTERN = "time_pattern"
    COMMITMENT_PATTERN = "commitment_pattern"
    STREAK_PATTERN = "streak_pattern"
    ENGAGEMENT_PATTERN = "engagement_pattern"

class PatternStrength(Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

@dataclass
class DetectedPattern:
    pattern_type: PatternType
    description: str
    strength: PatternStrength
    confidence: float
    data_points: List[Dict[str, Any]]
    actionable_insights: List[str]
    detected_at: datetime

class PatternRecognitionService:
    """Service for recognizing and analyzing user behavior patterns"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def analyze_user_patterns(self, user_id: str, days_back: int = 30) -> List[DetectedPattern]:
        """Analyze all patterns for a user over specified time period"""
        try:
            patterns = []
            
            # Analyze different pattern types
            usage_pattern = await self._analyze_usage_pattern(user_id, days_back)
            if usage_pattern:
                patterns.append(usage_pattern)
            
            response_pattern = await self._analyze_response_pattern(user_id, days_back)
            if response_pattern:
                patterns.append(response_pattern)
            
            time_pattern = await self._analyze_time_pattern(user_id, days_back)
            if time_pattern:
                patterns.append(time_pattern)
            
            commitment_pattern = await self._analyze_commitment_pattern(user_id, days_back)
            if commitment_pattern:
                patterns.append(commitment_pattern)
            
            streak_pattern = await self._analyze_streak_pattern(user_id, days_back)
            if streak_pattern:
                patterns.append(streak_pattern)
            
            engagement_pattern = await self._analyze_engagement_pattern(user_id, days_back)
            if engagement_pattern:
                patterns.append(engagement_pattern)
            
            logger.info(f"Analyzed {len(patterns)} patterns for user {user_id}")
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing patterns for {user_id}: {e}")
            return []
    
    async def _analyze_usage_pattern(self, user_id: str, days_back: int) -> Optional[DetectedPattern]:
        """Analyze usage patterns (when user opens app, frequency, etc.)"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            
            # Get chat messages to analyze usage
            messages_response = self.supabase.table('messages').select('*').eq(
                'user_id', user_id
            ).gte('created_at', cutoff_date).order('created_at', desc=True).execute()
            
            if not messages_response.data or len(messages_response.data) < 5:
                return None  # Not enough data
            
            messages = messages_response.data
            
            # Analyze usage frequency
            usage_dates = [datetime.fromisoformat(msg['created_at']).date() for msg in messages]
            unique_days = len(set(usage_dates))
            usage_rate = unique_days / days_back
            
            # Detect patterns
            patterns_detected = []
            insights = []
            data_points = []
            
            # Pattern 1: Daily user vs occasional user
            if usage_rate >= 0.8:
                patterns_detected.append("Daily user")
                insights.append("You're consistent with daily check-ins")
                confidence = 0.9
            elif usage_rate >= 0.5:
                patterns_detected.append("Regular user")
                insights.append("You have a solid routine established")
                confidence = 0.8
            elif usage_rate >= 0.3:
                patterns_detected.append("Occasional user")
                insights.append("You could benefit from more regular check-ins")
                confidence = 0.7
            else:
                patterns_detected.append("Sporadic user")
                insights.append("Consider setting a more consistent schedule")
                confidence = 0.6
            
            # Pattern 2: Time clustering
            usage_hours = [datetime.fromisoformat(msg['created_at']).hour for msg in messages]
            hour_counts = {}
            for hour in usage_hours:
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
            
            if hour_counts:
                most_common_hour = max(hour_counts, key=hour_counts.get)
                hour_percentage = hour_counts[most_common_hour] / len(usage_hours)
                
                if hour_percentage >= 0.4:
                    time_label = self._get_time_label(most_common_hour)
                    patterns_detected.append(f"Prefers {time_label}")
                    insights.append(f"You seem to prefer using the app in the {time_label.lower()}")
                    confidence = min(confidence + 0.1, 0.95)
            
            if patterns_detected:
                return DetectedPattern(
                    pattern_type=PatternType.USAGE_PATTERN,
                    description=f"Usage analysis: {', '.join(patterns_detected)}",
                    strength=self._calculate_strength(confidence),
                    confidence=confidence,
                    data_points=[{"usage_rate": usage_rate, "unique_days": unique_days, "total_messages": len(messages)}],
                    actionable_insights=insights,
                    detected_at=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing usage pattern: {e}")
            return None
    
    async def _analyze_response_pattern(self, user_id: str, days_back: int) -> Optional[DetectedPattern]:
        """Analyze response patterns (how quickly user responds to coach)"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            
            # Get messages to analyze response timing
            messages_response = self.supabase.table('messages').select('*').eq(
                'user_id', user_id
            ).gte('created_at', cutoff_date).order('created_at', asc=True).execute()
            
            if not messages_response.data or len(messages_response.data) < 10:
                return None
            
            messages = messages_response.data
            
            # Calculate response times
            response_times = []
            coach_messages = [msg for msg in messages if msg['direction'] == 'outgoing']
            
            for i, coach_msg in enumerate(coach_messages):
                # Find next user message after this coach message
                coach_time = datetime.fromisoformat(coach_msg['created_at'])
                next_user_msg = None
                
                # Look for user message after this coach message
                for j in range(i + 1, len(messages)):
                    if messages[j]['direction'] == 'incoming':
                        next_user_msg = messages[j]
                        break
                
                if next_user_msg:
                    user_time = datetime.fromisoformat(next_user_msg['created_at'])
                    response_time_hours = (user_time - coach_time).total_seconds() / 3600
                    if 0 < response_time_hours < 168:  # Less than a week
                        response_times.append(response_time_hours)
            
            if len(response_times) < 3:
                return None
            
            # Analyze response patterns
            avg_response_time = statistics.mean(response_times)
            median_response_time = statistics.median(response_times)
            
            insights = []
            patterns = []
            confidence = 0.8
            
            if avg_response_time <= 1:
                patterns.append("Quick responder")
                insights.append("You respond quickly to coach messages")
                confidence = 0.9
            elif avg_response_time <= 6:
                patterns.append("Regular responder")
                insights.append("You maintain good communication with your coach")
                confidence = 0.8
            elif avg_response_time <= 24:
                patterns.append("Slow responder")
                insights.append("Consider responding more frequently to stay engaged")
                confidence = 0.7
            else:
                patterns.append("Very slow responder")
                insights.append("Try to check in more regularly with your coach")
                confidence = 0.6
            
            # Check for consistency
            if len(response_times) >= 5:
                response_std = statistics.stdev(response_times)
                if response_std <= 2:
                    insights.append("Your response times are very consistent")
                    confidence = min(confidence + 0.1, 0.95)
                elif response_std <= 6:
                    insights.append("Your response times vary somewhat")
                else:
                    insights.append("Your response times are quite irregular")
            
            return DetectedPattern(
                pattern_type=PatternType.RESPONSE_PATTERN,
                description=f"Response analysis: {', '.join(patterns)}",
                strength=self._calculate_strength(confidence),
                confidence=confidence,
                data_points=[{"avg_response_hours": avg_response_time, "median_response_hours": median_response_time, "sample_size": len(response_times)}],
                actionable_insights=insights,
                detected_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error analyzing response pattern: {e}")
            return None
    
    async def _analyze_time_pattern(self, user_id: str, days_back: int) -> Optional[DetectedPattern]:
        """Analyze time-based patterns (preferred times, day of week, etc.)"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            
            messages_response = self.supabase.table('messages').select('*').eq(
                'user_id', user_id
            ).gte('created_at', cutoff_date).execute()
            
            if not messages_response.data or len(messages_response.data) < 10:
                return None
            
            messages = messages_response.data
            
            # Analyze day of week patterns
            days_of_week = {}
            for msg in messages:
                day_name = datetime.fromisoformat(msg['created_at']).strftime('%A')
                days_of_week[day_name] = days_of_week.get(day_name, 0) + 1
            
            if len(days_of_week) < 3:
                return None
            
            # Find most active day
            most_active_day = max(days_of_week, key=days_of_week.get)
            day_percentage = days_of_week[most_active_day] / len(messages)
            
            patterns = []
            insights = []
            confidence = 0.7
            
            if day_percentage >= 0.3:
                patterns.append(f"Most active on {most_active_day}")
                insights.append(f"You tend to be most engaged on {most_active_day}s")
                confidence = 0.8
            
            # Check for weekend vs weekday patterns
            weekend_activity = days_of_week.get('Saturday', 0) + days_of_week.get('Sunday', 0)
            weekday_activity = sum(count for day, count in days_of_week.items() 
                                 if day not in ['Saturday', 'Sunday'])
            
            if weekend_activity > 0 and weekday_activity > 0:
                weekend_percentage = weekend_activity / (weekend_activity + weekday_activity)
                if weekend_percentage >= 0.6:
                    patterns.append("Weekend-focused user")
                    insights.append("You prefer using the app on weekends")
                    confidence = min(confidence + 0.1, 0.9)
                elif weekend_percentage <= 0.3:
                    patterns.append("Weekday-focused user")
                    insights.append("You mainly use the app during weekdays")
                    confidence = min(confidence + 0.1, 0.9)
            
            if patterns:
                return DetectedPattern(
                    pattern_type=PatternType.TIME_PATTERN,
                    description=f"Time analysis: {', '.join(patterns)}",
                    strength=self._calculate_strength(confidence),
                    confidence=confidence,
                    data_points=[{"day_distribution": days_of_week, "most_active_day": most_active_day}],
                    actionable_insights=insights,
                    detected_at=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing time pattern: {e}")
            return None
    
    async def _analyze_commitment_pattern(self, user_id: str, days_back: int) -> Optional[DetectedPattern]:
        """Analyze commitment patterns (how user handles commitments)"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            
            commitments_response = self.supabase.table('commitments').select('*').eq(
                'user_id', user_id
            ).gte('created_at', cutoff_date).execute()
            
            if not commitments_response.data:
                return None
            
            commitments = commitments_response.data
            
            # Analyze commitment completion rates
            completed_count = sum(1 for c in commitments if c.get('status') == 'completed')
            total_count = len(commitments)
            completion_rate = completed_count / total_count if total_count > 0 else 0
            
            patterns = []
            insights = []
            confidence = 0.8
            
            if completion_rate >= 0.8:
                patterns.append("High commitment completion")
                insights.append("You consistently follow through on your commitments")
                confidence = 0.9
            elif completion_rate >= 0.6:
                patterns.append("Moderate commitment completion")
                insights.append("You complete most of your commitments")
                confidence = 0.8
            elif completion_rate >= 0.4:
                patterns.append("Low commitment completion")
                insights.append("Consider making smaller, more achievable commitments")
                confidence = 0.7
            else:
                patterns.append("Poor commitment completion")
                insights.append("Focus on commitments you're confident you can keep")
                confidence = 0.6
            
            # Analyze commitment types if available
            commitment_types = {}
            for c in commitments:
                commitment_text = c.get('commitment_text', '').lower()
                if 'daily' in commitment_text or 'every day' in commitment_text:
                    commitment_types['daily'] = commitment_types.get('daily', 0) + 1
                elif 'week' in commitment_text or 'weekly' in commitment_text:
                    commitment_types['weekly'] = commitment_types.get('weekly', 0) + 1
                else:
                    commitment_types['one_time'] = commitment_types.get('one_time', 0) + 1
            
            if commitment_types:
                most_common_type = max(commitment_types, key=commitment_types.get)
                if commitment_types[most_common_type] >= total_count * 0.6:
                    type_label = most_common_type.replace('_', ' ')
                    patterns.append(f"Prefers {type_label} commitments")
                    insights.append(f"You tend to make {type_label} commitments")
            
            if patterns:
                return DetectedPattern(
                    pattern_type=PatternType.COMMITMENT_PATTERN,
                    description=f"Commitment analysis: {', '.join(patterns)}",
                    strength=self._calculate_strength(confidence),
                    confidence=confidence,
                    data_points=[{"completion_rate": completion_rate, "total_commitments": total_count, "commitment_types": commitment_types}],
                    actionable_insights=insights,
                    detected_at=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing commitment pattern: {e}")
            return None
    
    async def _analyze_streak_pattern(self, user_id: str, days_back: int) -> Optional[DetectedPattern]:
        """Analyze streak patterns (consistency in maintaining streaks)"""
        try:
            streak_response = self.supabase.table('user_streaks').select('*').eq(
                'user_id', user_id
            ).execute()
            
            if not streak_response.data:
                return None
            
            streak_data = streak_response.data[0]
            current_streak = streak_data.get('current_streak', 0)
            longest_streak = streak_data.get('longest_streak', 0)
            
            patterns = []
            insights = []
            confidence = 0.8
            
            if current_streak >= 30:
                patterns.append("Long-term consistency")
                insights.append("You have excellent long-term consistency")
                confidence = 0.9
            elif current_streak >= 14:
                patterns.append("Strong current streak")
                insights.append("You're maintaining a strong streak right now")
                confidence = 0.8
            elif current_streak >= 7:
                patterns.append("Good streak momentum")
                insights.append("You're building good momentum with your streak")
                confidence = 0.7
            elif current_streak >= 3:
                patterns.append("Starting streak")
                insights.append("You're building a new streak")
                confidence = 0.6
            
            # Analyze streak consistency
            if longest_streak > 0:
                streak_ratio = current_streak / longest_streak if longest_streak > 0 else 0
                if streak_ratio >= 0.8:
                    insights.append("You're performing close to your personal best")
                    confidence = min(confidence + 0.1, 0.95)
                elif streak_ratio <= 0.3:
                    insights.append("You have room to get back to your personal best")
                    confidence = min(confidence + 0.1, 0.9)
            
            if patterns:
                return DetectedPattern(
                    pattern_type=PatternType.STREAK_PATTERN,
                    description=f"Streak analysis: {', '.join(patterns)}",
                    strength=self._calculate_strength(confidence),
                    confidence=confidence,
                    data_points=[{"current_streak": current_streak, "longest_streak": longest_streak}],
                    actionable_insights=insights,
                    detected_at=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing streak pattern: {e}")
            return None
    
    async def _analyze_engagement_pattern(self, user_id: str, days_back: int) -> Optional[DetectedPattern]:
        """Analyze engagement patterns (message frequency, depth, etc.)"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            
            messages_response = self.supabase.table('messages').select('*').eq(
                'user_id', user_id
            ).gte('created_at', cutoff_date).execute()
            
            if not messages_response.data or len(messages_response.data) < 10:
                return None
            
            messages = messages_response.data
            user_messages = [msg for msg in messages if msg['direction'] == 'incoming']
            
            if len(user_messages) < 5:
                return None
            
            # Analyze message length (as proxy for engagement depth)
            message_lengths = [len(msg.get('message_text', '')) for msg in user_messages]
            avg_length = statistics.mean(message_lengths)
            
            patterns = []
            insights = []
            confidence = 0.7
            
            if avg_length >= 100:
                patterns.append("Detailed communicator")
                insights.append("You provide detailed responses, showing high engagement")
                confidence = 0.8
            elif avg_length >= 50:
                patterns.append("Engaged communicator")
                insights.append("You maintain good engagement with detailed responses")
                confidence = 0.7
            elif avg_length >= 20:
                patterns.append("Brief communicator")
                insights.append("You prefer concise responses")
                confidence = 0.6
            else:
                patterns.append("Minimal communicator")
                insights.append("Consider sharing more details for better coaching")
                confidence = 0.5
            
            # Analyze message frequency
            days_with_messages = len(set(datetime.fromisoformat(msg['created_at']).date() 
                                        for msg in user_messages))
            message_frequency = len(user_messages) / days_with_messages if days_with_messages > 0 else 0
            
            if message_frequency >= 3:
                insights.append("You have multiple conversations per day")
                confidence = min(confidence + 0.1, 0.9)
            elif message_frequency >= 1.5:
                insights.append("You have regular daily conversations")
                confidence = min(confidence + 0.1, 0.8)
            
            if patterns:
                return DetectedPattern(
                    pattern_type=PatternType.ENGAGEMENT_PATTERN,
                    description=f"Engagement analysis: {', '.join(patterns)}",
                    strength=self._calculate_strength(confidence),
                    confidence=confidence,
                    data_points=[{"avg_message_length": avg_length, "total_messages": len(user_messages), "message_frequency": message_frequency}],
                    actionable_insights=insights,
                    detected_at=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing engagement pattern: {e}")
            return None
    
    def _calculate_strength(self, confidence: float) -> PatternStrength:
        """Calculate pattern strength based on confidence score"""
        if confidence >= 0.9:
            return PatternStrength.VERY_STRONG
        elif confidence >= 0.8:
            return PatternStrength.STRONG
        elif confidence >= 0.6:
            return PatternStrength.MODERATE
        else:
            return PatternStrength.WEAK
    
    def _get_time_label(self, hour: int) -> str:
        """Convert hour to time label"""
        if 5 <= hour < 12:
            return "Morning"
        elif 12 <= hour < 17:
            return "Afternoon"
        elif 17 <= hour < 22:
            return "Evening"
        else:
            return "Night"

# Global pattern recognition service instance
pattern_recognition_service = PatternRecognitionService()