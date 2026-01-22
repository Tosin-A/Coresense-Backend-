"""
Commitment Insights Engine
Analyzes user commitment patterns to generate meaningful AI-coach-interpreted insights.

Focuses on behavioral patterns from commitments:
- Time of day patterns
- Day of week patterns
- Streak patterns
- Completion rate trends
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from backend.database.supabase_client import get_supabase_client
from backend.config import get_settings

logger = logging.getLogger(__name__)


class InsightType(Enum):
    BEHAVIORAL = 'behavioral'  # Blue
    PROGRESS = 'progress'      # Green
    RISK = 'risk'              # Amber


class PatternType(Enum):
    TIME_OF_DAY = 'time_of_day'
    DAY_OF_WEEK = 'day_of_week'
    STREAK = 'streak'
    COMPLETION_RATE = 'completion_rate'


@dataclass
class PatternEvidence:
    """Evidence data for a pattern insight."""
    type: PatternType
    labels: List[str]
    values: List[float]
    highlight_index: Optional[int]
    trend_direction: str  # 'up', 'down', 'stable'
    trend_value: Optional[str]


@dataclass
class CommitmentInsight:
    """A single commitment-based insight."""
    id: str
    type: InsightType
    title: str
    coach_commentary: str
    evidence: PatternEvidence
    action_text: Optional[str]
    is_new: bool
    created_at: datetime


# Time windows for time-of-day analysis
TIME_WINDOWS = {
    'morning': (6, 12),   # 6am - 12pm
    'afternoon': (12, 17), # 12pm - 5pm
    'evening': (17, 21),   # 5pm - 9pm
    'night': (21, 6),      # 9pm - 6am (wraps around)
}

DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Minimum data requirements
MIN_COMMITMENTS_FOR_INSIGHTS = 5
MIN_DAYS_FOR_PATTERNS = 3


class CommitmentInsightsEngine:
    """Engine for analyzing commitment patterns and generating insights."""

    def __init__(self):
        self.supabase = get_supabase_client()
        self.settings = get_settings()

    async def analyze_user_patterns(self, user_id: str) -> Dict:
        """
        Run all pattern detectors and return insights screen data.

        Returns:
            {
                coach_summary: str | None,
                patterns: List[InsightData],
                has_enough_data: bool,
                days_until_enough_data: int | None
            }
        """
        try:
            # Fetch commitment data
            commitments = await self._fetch_user_commitments(user_id, days=30)

            # Check if we have enough data
            if len(commitments) < MIN_COMMITMENTS_FOR_INSIGHTS:
                days_needed = max(0, MIN_DAYS_FOR_PATTERNS - self._count_unique_days(commitments))
                return {
                    'coach_summary': None,
                    'patterns': [],
                    'has_enough_data': False,
                    'days_until_enough_data': days_needed if days_needed > 0 else MIN_DAYS_FOR_PATTERNS
                }

            # Run all pattern detectors in parallel
            results = await asyncio.gather(
                self._detect_time_of_day_pattern(commitments),
                self._detect_day_of_week_pattern(commitments),
                self._detect_streak_pattern(user_id, commitments),
                self._detect_completion_rate_trend(user_id, commitments),
                return_exceptions=True
            )

            # Collect valid insights
            insights = []
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Pattern detection failed: {result}")
                    continue
                if result is not None:
                    insights.append(result)

            # Sort by type priority (risk first, then behavioral, then progress)
            type_priority = {InsightType.RISK: 0, InsightType.BEHAVIORAL: 1, InsightType.PROGRESS: 2}
            insights.sort(key=lambda x: type_priority.get(x.type, 99))

            # Limit to 5 insights
            insights = insights[:5]

            # Add coach commentary using AI (optional, falls back to default)
            insights = await self._add_coach_commentary(insights)

            # Generate overall coach summary
            coach_summary = await self._generate_coach_summary(insights, commitments)

            # Convert to response format
            patterns = []
            for insight in insights:
                patterns.append({
                    'id': insight.id,
                    'type': insight.type.value,
                    'title': insight.title,
                    'coach_commentary': insight.coach_commentary,
                    'evidence': {
                        'type': insight.evidence.type.value,
                        'labels': insight.evidence.labels,
                        'values': insight.evidence.values,
                        'highlight_index': insight.evidence.highlight_index,
                        'trend_direction': insight.evidence.trend_direction,
                        'trend_value': insight.evidence.trend_value,
                    },
                    'action_text': insight.action_text,
                    'is_new': insight.is_new,
                    'created_at': insight.created_at.isoformat(),
                })

            return {
                'coach_summary': coach_summary,
                'patterns': patterns,
                'has_enough_data': True,
                'days_until_enough_data': None
            }

        except Exception as e:
            logger.error(f"Error analyzing patterns for user {user_id}: {e}")
            return {
                'coach_summary': None,
                'patterns': [],
                'has_enough_data': False,
                'days_until_enough_data': MIN_DAYS_FOR_PATTERNS
            }

    async def _fetch_user_commitments(self, user_id: str, days: int = 30) -> List[Dict]:
        """Fetch user commitments from the last N days."""
        try:
            start_date = (date.today() - timedelta(days=days)).isoformat()

            response = self.supabase.table('commitments').select(
                'id, commitment_text, status, created_at, completed_at, priority'
            ).eq('user_id', user_id).gte('created_at', start_date).execute()

            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching commitments: {e}")
            return []

    def _count_unique_days(self, commitments: List[Dict]) -> int:
        """Count unique days with commitments."""
        days = set()
        for c in commitments:
            if c.get('created_at'):
                day = c['created_at'][:10]
                days.add(day)
        return len(days)

    async def _detect_time_of_day_pattern(self, commitments: List[Dict]) -> Optional[CommitmentInsight]:
        """
        Detect when user completes commitments most effectively.
        Triggers if 40%+ concentration in one time window.
        """
        try:
            # Count completions by time window
            completed = [c for c in commitments if c.get('status') == 'completed' and c.get('completed_at')]

            if len(completed) < 5:
                return None

            window_counts = {'morning': 0, 'afternoon': 0, 'evening': 0, 'night': 0}

            for c in completed:
                try:
                    completed_at = datetime.fromisoformat(c['completed_at'].replace('Z', '+00:00'))
                    hour = completed_at.hour

                    if 6 <= hour < 12:
                        window_counts['morning'] += 1
                    elif 12 <= hour < 17:
                        window_counts['afternoon'] += 1
                    elif 17 <= hour < 21:
                        window_counts['evening'] += 1
                    else:
                        window_counts['night'] += 1
                except (ValueError, TypeError):
                    continue

            total = sum(window_counts.values())
            if total == 0:
                return None

            # Find peak window
            peak_window = max(window_counts, key=window_counts.get)
            peak_count = window_counts[peak_window]
            peak_percentage = (peak_count / total) * 100

            # Only trigger if 40%+ concentration
            if peak_percentage < 40:
                return None

            # Build evidence
            labels = ['Morning', 'Afternoon', 'Evening', 'Night']
            values = [window_counts['morning'], window_counts['afternoon'],
                     window_counts['evening'], window_counts['night']]
            highlight_index = ['morning', 'afternoon', 'evening', 'night'].index(peak_window)

            # Determine insight type
            insight_type = InsightType.BEHAVIORAL

            # Build title and commentary
            window_display = peak_window.capitalize()
            title = f"Your {window_display} Power Zone"

            commentary = f"You complete {int(peak_percentage)}% of your commitments in the {peak_window}. This is your productivity sweet spot."

            action_text = f"Schedule important tasks for {peak_window}"

            return CommitmentInsight(
                id=f"time-of-day-{user_id_hash(peak_window)}",
                type=insight_type,
                title=title,
                coach_commentary=commentary,
                evidence=PatternEvidence(
                    type=PatternType.TIME_OF_DAY,
                    labels=labels,
                    values=values,
                    highlight_index=highlight_index,
                    trend_direction='stable',
                    trend_value=f"{int(peak_percentage)}%",
                ),
                action_text=action_text,
                is_new=True,
                created_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Error detecting time-of-day pattern: {e}")
            return None

    async def _detect_day_of_week_pattern(self, commitments: List[Dict]) -> Optional[CommitmentInsight]:
        """
        Detect completion rate by day of week.
        Triggers if 1.5x variance between best/worst day.
        """
        try:
            # Group commitments by day of week
            day_created = {i: 0 for i in range(7)}
            day_completed = {i: 0 for i in range(7)}

            for c in commitments:
                try:
                    created_at = datetime.fromisoformat(c['created_at'].replace('Z', '+00:00'))
                    day_idx = created_at.weekday()
                    day_created[day_idx] += 1

                    if c.get('status') == 'completed':
                        day_completed[day_idx] += 1
                except (ValueError, TypeError):
                    continue

            # Calculate completion rates per day
            completion_rates = {}
            for day_idx in range(7):
                if day_created[day_idx] >= 2:  # Need at least 2 commitments
                    completion_rates[day_idx] = (day_completed[day_idx] / day_created[day_idx]) * 100

            if len(completion_rates) < 3:
                return None

            # Find best and worst days
            best_day = max(completion_rates, key=completion_rates.get)
            worst_day = min(completion_rates, key=completion_rates.get)
            best_rate = completion_rates[best_day]
            worst_rate = completion_rates[worst_day]

            # Check for 1.5x variance
            if worst_rate > 0 and best_rate / worst_rate < 1.5:
                return None

            if best_rate - worst_rate < 20:  # At least 20% difference
                return None

            # Build evidence
            labels = DAY_NAMES
            values = [completion_rates.get(i, 0) for i in range(7)]

            # Determine insight type based on variance
            insight_type = InsightType.BEHAVIORAL

            best_day_name = DAY_NAMES[best_day]
            worst_day_name = DAY_NAMES[worst_day]

            title = f"{best_day_name}s Are Your Day"
            commentary = f"You complete {int(best_rate)}% of commitments on {best_day_name}s, but only {int(worst_rate)}% on {worst_day_name}s."
            action_text = f"Plan challenging tasks for {best_day_name}s"

            return CommitmentInsight(
                id=f"day-of-week-{best_day}",
                type=insight_type,
                title=title,
                coach_commentary=commentary,
                evidence=PatternEvidence(
                    type=PatternType.DAY_OF_WEEK,
                    labels=labels,
                    values=values,
                    highlight_index=best_day,
                    trend_direction='stable',
                    trend_value=f"{int(best_rate)}%",
                ),
                action_text=action_text,
                is_new=True,
                created_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Error detecting day-of-week pattern: {e}")
            return None

    async def _detect_streak_pattern(self, user_id: str, commitments: List[Dict]) -> Optional[CommitmentInsight]:
        """
        Analyze streak patterns - current vs historical.
        Flags if current streak is <30% or >90% of longest.
        """
        try:
            # Fetch streak data
            streak_response = self.supabase.table('user_streaks').select(
                'current_streak, longest_streak'
            ).eq('user_id', user_id).limit(1).execute()

            if not streak_response.data:
                return None

            streak_data = streak_response.data[0]
            current = streak_data.get('current_streak', 0)
            longest = streak_data.get('longest_streak', 0)

            if longest < 3:  # Need meaningful streak history
                return None

            ratio = current / longest if longest > 0 else 0

            # Determine insight type and message
            if ratio < 0.3:
                # Risk: streak is significantly below potential
                insight_type = InsightType.RISK
                title = "Rebuild Your Momentum"
                commentary = f"Your current {current}-day streak is below your best ({longest} days). Let's get back on track!"
                action_text = "Complete one commitment today"
                trend_direction = 'down'
                trend_value = f"{current}/{longest} days"
            elif ratio > 0.9 and current >= 5:
                # Progress: approaching or at best
                insight_type = InsightType.PROGRESS
                title = "Streak Record in Sight!"
                commentary = f"You're at {current} days - just {longest - current} away from your record!"
                action_text = "Keep the momentum going"
                trend_direction = 'up'
                trend_value = f"{current} days"
            else:
                return None  # No significant pattern

            # Build chart data - show last 7 days of activity
            labels = [(date.today() - timedelta(days=i)).strftime('%a') for i in range(6, -1, -1)]

            # Simulate daily activity based on streak (simplified)
            values = []
            for i in range(6, -1, -1):
                if i < current:
                    values.append(1)
                else:
                    values.append(0)

            return CommitmentInsight(
                id=f"streak-{current}-{longest}",
                type=insight_type,
                title=title,
                coach_commentary=commentary,
                evidence=PatternEvidence(
                    type=PatternType.STREAK,
                    labels=labels,
                    values=values,
                    highlight_index=6 if current > 0 else None,
                    trend_direction=trend_direction,
                    trend_value=trend_value,
                ),
                action_text=action_text,
                is_new=True,
                created_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Error detecting streak pattern: {e}")
            return None

    async def _detect_completion_rate_trend(self, user_id: str, commitments: List[Dict]) -> Optional[CommitmentInsight]:
        """
        Detect completion rate trends (comparing recent vs previous period).
        Triggers if 15%+ change between periods.
        """
        try:
            # Split into recent (last 7 days) and previous (7-14 days ago)
            today = date.today()
            recent_start = today - timedelta(days=7)
            previous_start = today - timedelta(days=14)

            recent_commitments = []
            previous_commitments = []

            for c in commitments:
                try:
                    created_at = datetime.fromisoformat(c['created_at'].replace('Z', '+00:00')).date()
                    if created_at >= recent_start:
                        recent_commitments.append(c)
                    elif created_at >= previous_start:
                        previous_commitments.append(c)
                except (ValueError, TypeError):
                    continue

            # Need minimum data
            if len(recent_commitments) < 3 or len(previous_commitments) < 3:
                return None

            # Calculate completion rates
            recent_completed = len([c for c in recent_commitments if c.get('status') == 'completed'])
            previous_completed = len([c for c in previous_commitments if c.get('status') == 'completed'])

            recent_rate = (recent_completed / len(recent_commitments)) * 100
            previous_rate = (previous_completed / len(previous_commitments)) * 100

            # Check for 15%+ change
            change = recent_rate - previous_rate
            if abs(change) < 15:
                return None

            # Determine insight type and message
            if change > 0:
                insight_type = InsightType.PROGRESS
                title = "Momentum Building!"
                commentary = f"Your completion rate jumped to {int(recent_rate)}% this week, up {int(change)}% from last week."
                action_text = "Keep this energy going"
                trend_direction = 'up'
                trend_value = f"+{int(change)}%"
            else:
                insight_type = InsightType.RISK
                title = "Completion Rate Dip"
                commentary = f"Your completion rate dropped to {int(recent_rate)}% from {int(previous_rate)}% last week."
                action_text = "Start with one small win today"
                trend_direction = 'down'
                trend_value = f"{int(change)}%"

            # Build chart data - daily rates for last 14 days
            labels = [(today - timedelta(days=i)).strftime('%m/%d') for i in range(13, -1, -1)]

            # Calculate daily completion counts (simplified - shows the trend)
            values = []
            daily_data = {}

            for c in commitments:
                try:
                    created_at = datetime.fromisoformat(c['created_at'].replace('Z', '+00:00')).date()
                    day_str = created_at.strftime('%m/%d')
                    if day_str not in daily_data:
                        daily_data[day_str] = {'total': 0, 'completed': 0}
                    daily_data[day_str]['total'] += 1
                    if c.get('status') == 'completed':
                        daily_data[day_str]['completed'] += 1
                except (ValueError, TypeError):
                    continue

            for label in labels:
                if label in daily_data and daily_data[label]['total'] > 0:
                    rate = (daily_data[label]['completed'] / daily_data[label]['total']) * 100
                    values.append(rate)
                else:
                    values.append(0)

            return CommitmentInsight(
                id=f"completion-rate-{int(recent_rate)}",
                type=insight_type,
                title=title,
                coach_commentary=commentary,
                evidence=PatternEvidence(
                    type=PatternType.COMPLETION_RATE,
                    labels=labels[-7:],  # Show only last 7 days
                    values=values[-7:],
                    highlight_index=6,  # Highlight most recent
                    trend_direction=trend_direction,
                    trend_value=trend_value,
                ),
                action_text=action_text,
                is_new=True,
                created_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Error detecting completion rate trend: {e}")
            return None

    async def _add_coach_commentary(self, insights: List[CommitmentInsight]) -> List[CommitmentInsight]:
        """
        Add AI coach commentary to insights.
        Uses GPT-4 mini for brief, personalized commentary.
        Falls back to default commentary if AI unavailable.
        """
        # For now, return insights as-is (commentary already set in detectors)
        # AI enhancement can be added later
        return insights

    async def _generate_coach_summary(self, insights: List[CommitmentInsight], commitments: List[Dict]) -> Optional[str]:
        """Generate an overall coach summary based on insights."""
        if not insights:
            return None

        # Calculate overall completion rate
        completed = len([c for c in commitments if c.get('status') == 'completed'])
        total = len(commitments)
        rate = (completed / total * 100) if total > 0 else 0

        # Generate summary based on dominant insight types
        risk_count = len([i for i in insights if i.type == InsightType.RISK])
        progress_count = len([i for i in insights if i.type == InsightType.PROGRESS])

        if risk_count > progress_count:
            return f"I noticed some patterns that need attention. Your overall completion rate is {int(rate)}%. Let's work on building momentum."
        elif progress_count > risk_count:
            return f"Great progress! You're completing {int(rate)}% of your commitments. Keep leveraging your strengths."
        else:
            return f"You're completing {int(rate)}% of your commitments. Here are some patterns I noticed."

    async def get_active_insights(self, user_id: str) -> Dict:
        """Get active insights for display. Wrapper for analyze_user_patterns."""
        return await self.analyze_user_patterns(user_id)

    async def mark_insight_reaction(
        self,
        insight_id: str,
        user_id: str,
        helpful: bool
    ) -> bool:
        """Record user reaction to an insight."""
        try:
            interaction_type = 'helpful' if helpful else 'not_helpful'

            self.supabase.table('insight_interactions').insert({
                'insight_id': insight_id,
                'user_id': user_id,
                'interaction_type': interaction_type,
            }).execute()

            return True
        except Exception as e:
            logger.error(f"Error recording insight reaction: {e}")
            return False

    async def dismiss_insight(self, insight_id: str, user_id: str) -> bool:
        """Mark an insight as dismissed."""
        try:
            self.supabase.table('insight_interactions').insert({
                'insight_id': insight_id,
                'user_id': user_id,
                'interaction_type': 'dismissed',
            }).execute()

            return True
        except Exception as e:
            logger.error(f"Error dismissing insight: {e}")
            return False


def user_id_hash(value: str) -> str:
    """Generate a simple hash for IDs."""
    import hashlib
    return hashlib.md5(value.encode()).hexdigest()[:8]


# Global instance
commitment_insights_engine = CommitmentInsightsEngine()
