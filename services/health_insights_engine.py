"""
Health Insights Engine
Analyzes health-first patterns (sleep, activity, energy windows, weekend effect)
from user_health_data to generate immediate insights.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from statistics import pstdev
from typing import Dict, List, Optional, Tuple

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class InsightType(Enum):
    BEHAVIORAL = "behavioral"
    PROGRESS = "progress"
    RISK = "risk"


class PatternType(Enum):
    SLEEP_PATTERN = "sleep_pattern"
    ACTIVITY_CONSISTENCY = "activity_consistency"
    ENERGY_WINDOWS = "energy_windows"
    WEEKEND_EFFECT = "weekend_effect"
    # Check-in based patterns
    MOOD_PATTERN = "mood_pattern"
    CHECKIN_ENERGY_PATTERN = "checkin_energy_pattern"
    STRESS_PATTERN = "stress_pattern"


@dataclass
class PatternEvidence:
    type: PatternType
    labels: List[str]
    values: List[float]
    highlight_index: Optional[int]
    trend_direction: str
    trend_value: Optional[str]


@dataclass
class HealthInsight:
    id: str
    type: InsightType
    title: str
    coach_commentary: str
    evidence: PatternEvidence
    action_text: Optional[str]
    is_new: bool
    created_at: datetime
    action_steps: List[str] = None

    def __post_init__(self):
        if self.action_steps is None:
            self.action_steps = []


MIN_DAYS_FOR_INSIGHTS = 3  # Lowered from 7 to show insights sooner
MAX_DAYS = 14


class HealthInsightsEngine:
    def __init__(self):
        self.supabase = get_supabase_client()

    async def get_active_insights(self, user_id: str) -> Dict:
        try:
            logger.info(f"[HealthInsights] Getting active insights for user {user_id}")

            # Fetch both data sources in parallel
            health_data, metrics_data = await asyncio.gather(
                self._fetch_user_health_data(user_id, days=MAX_DAYS),
                self._fetch_user_metrics_data(user_id, days=MAX_DAYS),
            )

            days_with_health = self._count_days_with_data(health_data)
            days_with_metrics = self._count_days_with_metrics(metrics_data)
            days_with_data = max(days_with_health, days_with_metrics)

            logger.info(f"[HealthInsights] Health days: {days_with_health}, Metrics days: {days_with_metrics}, min_required: {MIN_DAYS_FOR_INSIGHTS}")

            if days_with_data < MIN_DAYS_FOR_INSIGHTS:
                return {
                    "coach_summary": None,
                    "patterns": [],
                    "has_enough_data": False,
                    "days_until_enough_data": max(1, MIN_DAYS_FOR_INSIGHTS - days_with_data),
                }

            # Run all analyzers in parallel (4 health-based + 3 check-in based)
            results = await asyncio.gather(
                # Existing health-based analyzers
                self._analyze_sleep_patterns(user_id, health_data),
                self._analyze_energy_windows(user_id, health_data),
                self._analyze_activity_consistency(user_id, health_data),
                self._analyze_weekend_effect(user_id, health_data),
                # Check-in based analyzers
                self._analyze_mood_patterns(user_id, metrics_data),
                self._analyze_checkin_energy_patterns(user_id, metrics_data, health_data),
                self._analyze_stress_patterns(user_id, metrics_data),
                return_exceptions=True,
            )

            pattern_names = [
                "sleep", "energy_windows", "activity", "weekend_effect",
                "mood", "checkin_energy", "stress"
            ]

            insights: List[HealthInsight] = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"[HealthInsights] Pattern {pattern_names[i]} failed: {result}")
                    continue
                if result is None:
                    logger.info(f"[HealthInsights] Pattern {pattern_names[i]} returned None (insufficient data)")
                elif result["confidence"] < 0.25:  # Lowered from 0.4 to show more insights
                    logger.info(f"[HealthInsights] Pattern {pattern_names[i]} confidence {result['confidence']:.2f} < 0.25, skipping")
                else:
                    logger.info(f"[HealthInsights] Pattern {pattern_names[i]} generated with confidence {result['confidence']:.2f}")
                    insights.append(result["insight"])

            type_priority = {
                InsightType.RISK: 0,
                InsightType.BEHAVIORAL: 1,
                InsightType.PROGRESS: 2,
            }
            insights.sort(key=lambda x: type_priority.get(x.type, 99))
            insights = insights[:5]

            has_risk = any(i.type == InsightType.RISK for i in insights)
            has_checkin_insights = any(
                i.evidence.type in (PatternType.MOOD_PATTERN, PatternType.CHECKIN_ENERGY_PATTERN, PatternType.STRESS_PATTERN)
                for i in insights
            )
            data_source = "your health and check-in data" if has_checkin_insights else "your health data"
            coach_summary = (
                f"Looked at {data_source} from the last week. "
                f"Found {len(insights)} pattern{'s' if len(insights) != 1 else ''}"
                f"{' — some need attention' if has_risk else ' worth knowing about'}."
                if insights
                else None
            )

            patterns = [
                {
                    "id": insight.id,
                    "type": insight.type.value,
                    "title": insight.title,
                    "coach_commentary": insight.coach_commentary,
                    "evidence": {
                        "type": insight.evidence.type.value,
                        "labels": insight.evidence.labels,
                        "values": insight.evidence.values,
                        "highlight_index": insight.evidence.highlight_index,
                        "trend_direction": insight.evidence.trend_direction,
                        "trend_value": insight.evidence.trend_value,
                    },
                    "action_text": insight.action_text,
                    "action_steps": insight.action_steps,
                    "is_new": insight.is_new,
                    "created_at": insight.created_at.isoformat(),
                }
                for insight in insights
            ]

            return {
                "coach_summary": coach_summary,
                "patterns": patterns,
                "has_enough_data": True,
                "days_until_enough_data": None,
            }

        except Exception as e:
            logger.error(f"Error generating health insights for user {user_id}: {e}")
            return {
                "coach_summary": None,
                "patterns": [],
                "has_enough_data": False,
                "days_until_enough_data": MIN_DAYS_FOR_INSIGHTS,
            }

    async def _fetch_user_health_data(self, user_id: str, days: int) -> List[Dict]:
        """Fetch daily health data aggregated from health_metrics via database view."""
        try:
            # Use UTC date to ensure consistency with stored timestamps
            from datetime import timezone as tz
            today_utc = datetime.now(tz.utc).date()
            start_date = (today_utc - timedelta(days=days - 1)).isoformat()

            logger.info(f"[HealthInsights] Fetching data for user {user_id}, start_date={start_date}")

            # Query the aggregation view with all fields including sleep times
            response = (
                self.supabase.table("health_metrics_daily")
                .select(
                    "date,sleep_duration_hours,sleep_start_hour,sleep_end_hour,"
                    "steps,active_energy,"
                    "avg_heart_rate,resting_heart_rate,data_completeness"
                )
                .eq("user_id", user_id)
                .gte("date", start_date)
                .order("date")
                .execute()
            )
            data = response.data or []

            logger.info(f"[HealthInsights] View returned {len(data)} rows")
            if data:
                # Log detailed data for debugging
                sleep_days = [r for r in data if r.get("sleep_duration_hours") and float(r.get("sleep_duration_hours", 0)) > 0]
                sleep_start_days = [r for r in data if r.get("sleep_start_hour") is not None]
                sleep_end_days = [r for r in data if r.get("sleep_end_hour") is not None]
                steps_days = [r for r in data if r.get("steps") and int(r.get("steps", 0)) > 0]
                logger.info(f"[HealthInsights] Days with sleep_duration: {len(sleep_days)}, sleep_start: {len(sleep_start_days)}, sleep_end: {len(sleep_end_days)}, steps: {len(steps_days)}")

                # Log sample sleep values for debugging
                if sleep_days:
                    sample = sleep_days[0]
                    logger.info(f"[HealthInsights] Sample sleep data: date={sample.get('date')}, duration={sample.get('sleep_duration_hours')}, start={sample.get('sleep_start_hour')}, end={sample.get('sleep_end_hour')}")

            if data:
                # Add null fields for compatibility with pattern analysis methods
                for row in data:
                    row["hourly_activity"] = None
                    row["active_minutes"] = None
                    row["exercise_minutes"] = None
                    row["sedentary_minutes"] = None
                return data

            # Fallback: aggregate raw health_metrics if view query fails
            logger.info(f"[HealthInsights] View empty, falling back to direct aggregation")
            return self._aggregate_health_metrics(user_id, start_date)
        except Exception as e:
            logger.error(f"Error fetching health data: {e}")
            # Fallback to direct aggregation
            from datetime import timezone as tz
            today_utc = datetime.now(tz.utc).date()
            start_date = (today_utc - timedelta(days=days - 1)).isoformat()
            return self._aggregate_health_metrics(user_id, start_date)

    def _aggregate_health_metrics(self, user_id: str, start_date: str) -> List[Dict]:
        """Fallback aggregation when database view is not available."""
        try:
            logger.info(f"[HealthInsights] Aggregating raw health_metrics since {start_date}")
            response = (
                self.supabase.table("health_metrics")
                .select("metric_type,value,recorded_at")
                .eq("user_id", user_id)
                .gte("recorded_at", start_date)
                .execute()
            )
            rows = response.data or []
            logger.info(f"[HealthInsights] Raw health_metrics returned {len(rows)} rows")
            if not rows:
                return []

            daily: Dict[str, Dict] = {}
            for row in rows:
                metric_type = row.get("metric_type")
                value = float(row.get("value") or 0)
                recorded_at = row.get("recorded_at") or ""
                day = recorded_at[:10]
                if not day:
                    continue
                daily.setdefault(
                    day,
                    {
                        "date": day,
                        "sleep_duration_hours": None,
                        "sleep_start_hour": None,
                        "sleep_end_hour": None,
                        "steps": None,
                        "active_energy": None,
                        "avg_heart_rate": None,
                        "active_minutes": None,
                        "exercise_minutes": None,
                        "sedentary_minutes": None,
                        "hourly_activity": None,
                    },
                )
                if metric_type == "sleep_duration":
                    current = daily[day]["sleep_duration_hours"] or 0
                    daily[day]["sleep_duration_hours"] = current + value
                elif metric_type == "sleep_start":
                    # Take earliest bedtime (min value)
                    current = daily[day]["sleep_start_hour"]
                    if current is None or value < current:
                        daily[day]["sleep_start_hour"] = value
                elif metric_type == "sleep_end":
                    # Take latest wake time (max value)
                    current = daily[day]["sleep_end_hour"]
                    if current is None or value > current:
                        daily[day]["sleep_end_hour"] = value
                elif metric_type == "steps":
                    current = daily[day]["steps"] or 0
                    daily[day]["steps"] = current + int(value)
                elif metric_type == "active_energy":
                    current = daily[day]["active_energy"] or 0
                    daily[day]["active_energy"] = current + value

            aggregated = [daily[day] for day in sorted(daily.keys())]
            # Log aggregated data summary
            sleep_days = [d for d in aggregated if d.get("sleep_duration_hours")]
            steps_days = [d for d in aggregated if d.get("steps")]
            logger.info(f"[HealthInsights] Fallback aggregation: {len(aggregated)} days, {len(sleep_days)} with sleep, {len(steps_days)} with steps")
            return aggregated
        except Exception as e:
            logger.error(f"Error aggregating health_metrics: {e}")
            return []

    def _count_days_with_data(self, health_data: List[Dict]) -> int:
        days = set()
        for row in health_data:
            if row.get("sleep_duration_hours") is not None or row.get("steps") is not None:
                days.add(row.get("date"))
        return len(days)

    async def _analyze_sleep_patterns(self, user_id: str, health_data: List[Dict]) -> Optional[Dict]:
        sleep_rows = [r for r in health_data if r.get("sleep_duration_hours") is not None]
        if len(sleep_rows) < 2:  # Lowered from 4 to show sleep insights sooner
            return None

        sleep_values = [float(r["sleep_duration_hours"]) for r in sleep_rows]
        avg_sleep = sum(sleep_values) / len(sleep_values)
        sleep_std = pstdev(sleep_values) if len(sleep_values) > 1 else 0

        weekday_avg, weekend_avg = self._weekday_weekend_avgs(sleep_rows, "sleep_duration_hours")

        pattern_strength = min(1.0, abs(avg_sleep - 7.0) / 2.0)
        confidence = self._confidence(len(sleep_rows), pattern_strength)

        labels, values = self._last_7_days_series(health_data, "sleep_duration_hours")
        highlight_index = self._highlight_min_index(values)

        if avg_sleep < 6.5:
            insight_type = InsightType.RISK
            commentary = (
                f"You're getting {avg_sleep:.1f} hours on average. That's why you feel like crap."
            )
            action_steps = [
                "Set a hard bedtime alarm 8 hours before your wake time",
                "No screens 30 minutes before bed",
                "If you can, schedule a 20-minute power nap between 1-3 PM",
            ]
        elif avg_sleep < 7.2:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"You're averaging {avg_sleep:.1f} hours. You're flirting with sleep debt."
            action_steps = [
                "Move your bedtime back by 15 minutes this week",
                "Reduce caffeine after 2 PM",
                "Track what keeps you up - phone, racing thoughts, or environment",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"You're averaging {avg_sleep:.1f} hours. That's a solid base to build on."
            action_steps = [
                "Maintain your current sleep schedule on weekends too",
                "Notice how sleep quality affects next-day energy and focus",
            ]

        trend_direction = "down" if avg_sleep < 7 else "up"
        trend_value = f"{avg_sleep:.1f}h avg"

        insight = HealthInsight(
            id=f"sleep-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Your Sleep Rhythm",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.SLEEP_PATTERN,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction=trend_direction,
                trend_value=trend_value,
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.SLEEP_PATTERN.value,
            confidence=confidence,
            pattern_data={
                "avg_sleep": round(avg_sleep, 2),
                "sleep_std": round(sleep_std, 2),
                "weekday_avg": weekday_avg,
                "weekend_avg": weekend_avg,
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_energy_windows(self, user_id: str, health_data: List[Dict]) -> Optional[Dict]:
        """Analyze energy windows using sleep schedule (bedtime/wake time) data."""
        sleep_rows = [
            r for r in health_data
            if r.get("sleep_start_hour") is not None and r.get("sleep_end_hour") is not None
        ]

        if len(sleep_rows) < 2:  # Lowered from 4 to show energy insights sooner
            return None

        bedtimes = [float(r["sleep_start_hour"]) for r in sleep_rows]
        wake_times = [float(r["sleep_end_hour"]) for r in sleep_rows]

        avg_bedtime = sum(bedtimes) / len(bedtimes)
        avg_wake = sum(wake_times) / len(wake_times)

        # Determine active window: wake time to bedtime
        active_hours = avg_bedtime - avg_wake if avg_bedtime > avg_wake else (24 - avg_wake + avg_bedtime)

        # Classify as morning/evening person based on wake time
        is_morning_person = avg_wake < 7.0
        is_night_person = avg_bedtime >= 23.0 or avg_bedtime < 2.0

        # Pattern strength based on how clear the schedule is
        bedtime_std = pstdev(bedtimes) if len(bedtimes) > 1 else 0
        wake_std = pstdev(wake_times) if len(wake_times) > 1 else 0
        consistency = max(0.0, 1.0 - (bedtime_std + wake_std) / 4.0)
        pattern_strength = max(0.3, consistency)
        confidence = self._confidence(len(sleep_rows), pattern_strength)

        wake_label = self._hour_label(int(avg_wake))
        bed_label = self._hour_label(int(avg_bedtime) % 24)

        if is_morning_person:
            commentary = f"You're up by {wake_label} most days. Front-load your important work."
            insight_type = InsightType.PROGRESS
            peak_window = f"{wake_label}-{self._hour_label(int(avg_wake) + 4)}"
            action_steps = [
                "Block your first 3 hours after waking for deep work",
                "Protect mornings from meetings when possible",
                "Use afternoon for admin and routine tasks",
            ]
        elif is_night_person:
            commentary = f"You're a night owl. Most active after 8pm. Stop pretending mornings work."
            insight_type = InsightType.BEHAVIORAL
            peak_window = f"8pm-{bed_label}"
            action_steps = [
                "Don't fight your rhythm - schedule creative work in the evening",
                "Use mornings for routine tasks, not deep thinking",
                "Consider a 20-minute power nap between 2-4 PM if energy dips",
            ]
        else:
            midpoint = (avg_wake + avg_bedtime) / 2
            peak_start = int(midpoint - 1.5) % 24
            peak_window = self._format_hour_window(peak_start, 3)
            commentary = f"Your energy peaks {peak_window}. Use that window for hard tasks."
            insight_type = InsightType.BEHAVIORAL
            action_steps = [
                "Experiment with scheduling focus work at different times this week",
                "Track your energy levels hourly for 3 days to find your pattern",
            ]

        # Build chart: last 7 days showing bedtime and wake time
        labels = []
        bedtime_values = []
        wake_values = []
        if sleep_rows:
            last_date = self._parse_date(sleep_rows[-1].get("date")) or date.today()
        else:
            last_date = date.today()

        data_map = {}
        for r in sleep_rows:
            d = self._parse_date(r.get("date"))
            if d:
                data_map[d] = r

        for delta in reversed(range(7)):
            d = last_date - timedelta(days=delta)
            labels.append(d.strftime("%a"))
            row = data_map.get(d)
            if row:
                # Normalize bedtime for chart (show as hours past noon for visual clarity)
                bt = float(row.get("sleep_start_hour", 0))
                wt = float(row.get("sleep_end_hour", 0))
                bedtime_values.append(round(bt, 1))
                wake_values.append(round(wt, 1))
            else:
                bedtime_values.append(0)
                wake_values.append(0)

        insight = HealthInsight(
            id=f"energy-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Your Energy Pattern",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.ENERGY_WINDOWS,
                labels=labels,
                values=wake_values,
                highlight_index=None,
                trend_direction="stable",
                trend_value=peak_window,
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.ENERGY_WINDOWS.value,
            confidence=confidence,
            pattern_data={
                "avg_bedtime": round(avg_bedtime, 1),
                "avg_wake": round(avg_wake, 1),
                "peak_window": peak_window,
                "is_morning_person": is_morning_person,
                "is_night_person": is_night_person,
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_activity_consistency(
        self, user_id: str, health_data: List[Dict]
    ) -> Optional[Dict]:
        step_rows = [r for r in health_data if r.get("steps") is not None and float(r["steps"]) > 0]
        if len(step_rows) < 2:  # Lowered from 4 to show activity insights sooner
            return None

        step_values = [float(r["steps"]) for r in step_rows]
        avg_steps = sum(step_values) / len(step_values)
        if avg_steps <= 0:
            return None

        step_std = pstdev(step_values) if len(step_values) > 1 else 0
        cv = step_std / avg_steps if avg_steps else 0
        max_steps = max(step_values)
        min_steps = min(step_values)

        # Pattern strength: any clear activity pattern is interesting
        # High CV = inconsistent (risk insight), Low CV = consistent (progress insight)
        pattern_strength = max(0.5, min(1.0, cv / 0.5)) if cv >= 0.3 else max(0.5, 1.0 - cv)
        confidence = self._confidence(len(step_rows), pattern_strength)

        labels, values = self._last_7_days_series(health_data, "steps")
        highlight_index = self._highlight_max_index(values)

        if cv >= 0.6:
            commentary = (
                f"You move a lot some days ({int(max_steps):,} steps), "
                f"then nothing ({int(min_steps):,}). All or nothing."
            )
            insight_type = InsightType.RISK
            action_steps = [
                f"Set a minimum daily floor of {int(min_steps + (avg_steps - min_steps) * 0.3):,} steps",
                "On low-activity days, take a 15-minute walk after lunch",
                "Track what kills your movement on zero days",
            ]
        elif cv >= 0.35:
            commentary = (
                f"Averaging {int(avg_steps):,} steps but with big swings. "
                f"Build a daily floor you can hit consistently."
            )
            insight_type = InsightType.BEHAVIORAL
            action_steps = [
                f"Aim for at least {int(avg_steps * 0.8):,} steps every day this week",
                "Schedule movement at the same time each day to build habit",
            ]
        else:
            commentary = (
                f"Averaging {int(avg_steps):,} steps with steady consistency. "
                f"That's a solid movement habit."
            )
            insight_type = InsightType.PROGRESS
            action_steps = [
                f"You're consistent - try bumping your target to {int(avg_steps * 1.1):,} steps",
                "Add one 20-minute walk on your best energy day",
            ]

        insight = HealthInsight(
            id=f"activity-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Movement Patterns",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.ACTIVITY_CONSISTENCY,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction="down" if cv >= 0.5 else "up" if cv < 0.3 else "stable",
                trend_value=f"{int(avg_steps):,} avg steps",
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.ACTIVITY_CONSISTENCY.value,
            confidence=confidence,
            pattern_data={
                "avg_steps": round(avg_steps),
                "cv": round(cv, 2),
                "max_steps": round(max_steps),
                "min_steps": round(min_steps),
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_weekend_effect(self, user_id: str, health_data: List[Dict]) -> Optional[Dict]:
        weekday_steps, weekend_steps = self._weekday_weekend_avgs(health_data, "steps")
        weekday_sleep, weekend_sleep = self._weekday_weekend_avgs(health_data, "sleep_duration_hours")

        # Need at least one metric pair to compare
        has_steps = weekday_steps is not None and weekend_steps is not None
        has_sleep = weekday_sleep is not None and weekend_sleep is not None

        if not has_steps and not has_sleep:
            return None

        step_diff = 0.0
        sleep_diff = 0.0

        if has_steps and weekday_steps > 0:
            step_diff = (weekday_steps - weekend_steps) / weekday_steps
        if has_sleep and weekday_sleep > 0:
            sleep_diff = (weekday_sleep - weekend_sleep) / weekday_sleep

        # Any noticeable difference is worth reporting
        max_diff = max(abs(step_diff), abs(sleep_diff))
        pattern_strength = max(0.4, min(1.0, max_diff / 0.3))
        confidence = self._confidence(len(health_data), pattern_strength)

        # Build labels and values - show both metrics if available
        labels = []
        values = []
        if has_steps:
            labels = ["Weekday Steps", "Weekend Steps"]
            values = [round(weekday_steps), round(weekend_steps)]

        if has_sleep:
            if has_steps:
                labels.extend(["Weekday Sleep", "Weekend Sleep"])
                values.extend([round(weekday_sleep, 1), round(weekend_sleep, 1)])
            else:
                labels = ["Weekday Sleep", "Weekend Sleep"]
                values = [round(weekday_sleep, 1), round(weekend_sleep, 1)]

        # Commentary based on what's different
        parts = []
        if has_steps and abs(step_diff) > 0.15:
            direction = "drops" if step_diff > 0 else "jumps"
            parts.append(f"activity {direction} {abs(step_diff) * 100:.0f}%")
        if has_sleep and abs(sleep_diff) > 0.1:
            direction = "drops" if sleep_diff > 0 else "increases"
            parts.append(f"sleep {direction} {abs(sleep_diff) * 100:.0f}%")

        if max_diff > 0.15:
            commentary = f"Weekend {', '.join(parts)}. It throws off your week."
            insight_type = InsightType.RISK
            action_steps = [
                "Keep weekend wake time within 1 hour of your weekday schedule",
                "Plan one active outing each weekend day",
                "Sunday evening prep routine: set clothes, meals, and top 3 priorities",
            ]
        elif parts:
            commentary = f"Weekend {', '.join(parts)}. It throws off your week."
            insight_type = InsightType.BEHAVIORAL
            action_steps = [
                "Your weekends are slightly different - that's normal",
                "Try one weekend morning with your weekday routine",
            ]
        else:
            commentary = "Your weekends look steady. Keep the rhythm consistent."
            insight_type = InsightType.PROGRESS
            action_steps = [
                "Great weekend consistency - this helps your body clock stay calibrated",
                "Keep it up and you'll see better Monday energy",
            ]

        highlight_index = 1  # highlight weekend value

        insight = HealthInsight(
            id=f"weekend-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="The Weekend Effect",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.WEEKEND_EFFECT,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction="down" if max_diff > 0.1 else "stable",
                trend_value=f"{max_diff * 100:.0f}% difference",
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.WEEKEND_EFFECT.value,
            confidence=confidence,
            pattern_data={
                "weekday_steps": round(weekday_steps) if weekday_steps else None,
                "weekend_steps": round(weekend_steps) if weekend_steps else None,
                "weekday_sleep": round(weekday_sleep, 1) if weekday_sleep else None,
                "weekend_sleep": round(weekend_sleep, 1) if weekend_sleep else None,
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}

    def _confidence(self, sample_size: int, pattern_strength: float) -> float:
        # Use MIN_DAYS_FOR_INSIGHTS as denominator so 7 days of data = 1.0 sample factor
        sample_factor = min(1.0, sample_size / MIN_DAYS_FOR_INSIGHTS)
        return min(1.0, sample_factor * pattern_strength)

    def _upsert_pattern(
        self,
        user_id: str,
        pattern_type: str,
        confidence: float,
        pattern_data: Dict,
        insight_title: Optional[str] = None,
    ) -> None:
        try:
            # Check if this is a new pattern (not seen before)
            existing = self.supabase.table("user_health_patterns").select(
                "id, confidence_score"
            ).eq("user_id", user_id).eq("pattern_type", pattern_type).execute()

            is_new_pattern = not existing.data or len(existing.data) == 0

            # Upsert the pattern
            result = self.supabase.table("user_health_patterns").upsert(
                {
                    "user_id": user_id,
                    "pattern_type": pattern_type,
                    "confidence_score": round(confidence, 2),
                    "pattern_data": pattern_data,
                    "calculated_at": datetime.utcnow().isoformat(),
                    "valid_until": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                },
                on_conflict="user_id,pattern_type",
            ).execute()

            # Log new patterns with high confidence (notifications handled separately)
            if is_new_pattern and confidence >= 0.6 and insight_title:
                logger.info(f"New insight discovered for {user_id}: {pattern_type} - {insight_title}")

        except Exception as e:
            logger.warning(f"Failed to upsert health pattern: {e}")

    def _weekday_weekend_avgs(
        self, rows: List[Dict], field: str
    ) -> Tuple[Optional[float], Optional[float]]:
        weekday_vals = []
        weekend_vals = []
        for row in rows:
            value = row.get(field)
            if value is None:
                continue
            row_date = self._parse_date(row.get("date"))
            if not row_date:
                continue
            if row_date.weekday() >= 5:
                weekend_vals.append(float(value))
            else:
                weekday_vals.append(float(value))

        weekday_avg = (
            sum(weekday_vals) / len(weekday_vals) if weekday_vals else None
        )
        weekend_avg = (
            sum(weekend_vals) / len(weekend_vals) if weekend_vals else None
        )
        return weekday_avg, weekend_avg

    def _last_7_days_series(
        self, rows: List[Dict], field: str
    ) -> Tuple[List[str], List[float]]:
        if rows:
            last_date = self._parse_date(rows[-1].get("date")) or date.today()
        else:
            last_date = date.today()

        series_dates = [
            last_date - timedelta(days=delta) for delta in reversed(range(7))
        ]
        data_map = {
            self._parse_date(r.get("date")): r.get(field) for r in rows
        }
        labels = [d.strftime("%a") for d in series_dates]
        values = [
            round(float(data_map.get(d, 0) or 0), 2) for d in series_dates
        ]
        return labels, values

    def _highlight_min_index(self, values: List[float]) -> Optional[int]:
        non_zero = [v for v in values if v > 0]
        if not non_zero:
            return None
        min_value = min(non_zero)
        return values.index(min_value)

    def _highlight_max_index(self, values: List[float]) -> Optional[int]:
        if not values:
            return None
        return int(values.index(max(values)))

    def _peak_window(self, values: List[float], window: int) -> Tuple[int, float]:
        best_start = 0
        best_sum = -1
        for start in range(24):
            total = 0
            for i in range(window):
                total += values[(start + i) % 24]
            if total > best_sum:
                best_sum = total
                best_start = start
        return best_start, best_sum

    def _format_hour_window(self, start_hour: int, window: int) -> str:
        end_hour = (start_hour + window) % 24
        return f"{self._hour_label(start_hour)}-{self._hour_label(end_hour)}"

    def _hour_label(self, hour: int) -> str:
        suffix = "am" if hour < 12 else "pm"
        hour12 = hour % 12
        hour12 = 12 if hour12 == 0 else hour12
        return f"{hour12}{suffix}"

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None

    # =========================================================================
    # Check-in Data Methods (mood, energy, stress from user_metrics table)
    # =========================================================================

    async def _fetch_user_metrics_data(self, user_id: str, days: int) -> List[Dict]:
        """Fetch daily check-in data (mood, energy, stress) from user_metrics table."""
        try:
            from datetime import timezone as tz
            today_utc = datetime.now(tz.utc).date()
            start_date = (today_utc - timedelta(days=days - 1)).isoformat()

            logger.info(f"[HealthInsights] Fetching user_metrics for user {user_id}, start_date={start_date}")

            response = (
                self.supabase.table("user_metrics")
                .select("metric_type,value,logged_at,context")
                .eq("user_id", user_id)
                .in_("metric_type", ["mood", "energy", "stress"])
                .gte("logged_at", start_date)
                .order("logged_at")
                .execute()
            )

            rows = response.data or []
            logger.info(f"[HealthInsights] user_metrics returned {len(rows)} rows")

            if not rows:
                return []

            return self._aggregate_metrics_by_day(rows)
        except Exception as e:
            logger.error(f"Error fetching user metrics: {e}")
            return []

    def _aggregate_metrics_by_day(self, rows: List[Dict]) -> List[Dict]:
        """Aggregate user_metrics rows into daily summaries."""
        daily: Dict[str, Dict] = {}
        for row in rows:
            logged_at = row.get("logged_at") or ""
            day = logged_at[:10]  # Extract date part
            if not day:
                continue

            if day not in daily:
                daily[day] = {
                    "date": day,
                    "mood_values": [],
                    "energy_values": [],
                    "stress_values": [],
                }

            metric_type = row.get("metric_type")
            value = float(row.get("value", 0))

            if metric_type == "mood":
                daily[day]["mood_values"].append(value)
            elif metric_type == "energy":
                daily[day]["energy_values"].append(value)
            elif metric_type == "stress":
                daily[day]["stress_values"].append(value)

        # Calculate daily averages
        result = []
        for day in sorted(daily.keys()):
            d = daily[day]
            result.append({
                "date": day,
                "avg_mood": sum(d["mood_values"]) / len(d["mood_values"]) if d["mood_values"] else None,
                "avg_energy": sum(d["energy_values"]) / len(d["energy_values"]) if d["energy_values"] else None,
                "avg_stress": sum(d["stress_values"]) / len(d["stress_values"]) if d["stress_values"] else None,
                "mood_count": len(d["mood_values"]),
                "energy_count": len(d["energy_values"]),
                "stress_count": len(d["stress_values"]),
            })

        logger.info(f"[HealthInsights] Aggregated metrics: {len(result)} days with check-ins")
        return result

    def _count_days_with_metrics(self, metrics_data: List[Dict]) -> int:
        """Count days with at least one metric logged."""
        days = set()
        for row in metrics_data:
            if row.get("avg_mood") is not None or row.get("avg_energy") is not None or row.get("avg_stress") is not None:
                days.add(row.get("date"))
        return len(days)

    def _day_of_week_avgs(self, rows: List[Dict], field: str) -> Dict[str, float]:
        """Calculate average for each day of the week."""
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        dow_values: Dict[int, List[float]] = {i: [] for i in range(7)}

        for row in rows:
            value = row.get(field)
            if value is None:
                continue
            row_date = self._parse_date(row.get("date"))
            if not row_date:
                continue
            dow_values[row_date.weekday()].append(float(value))

        result = {}
        for dow, values in dow_values.items():
            if values:
                result[dow_names[dow]] = sum(values) / len(values)
        return result

    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate trend as difference between last third and first third of values."""
        if len(values) < 3:
            return 0.0
        third = max(1, len(values) // 3)
        first_avg = sum(values[:third]) / third
        last_avg = sum(values[-third:]) / third
        return last_avg - first_avg

    def _correlate_with_sleep(self, energy_rows: List[Dict], health_data: List[Dict]) -> Optional[float]:
        """Get average sleep hours for days where we have energy data."""
        if not health_data:
            return None

        sleep_by_date = {}
        for row in health_data:
            if row.get("sleep_duration_hours"):
                sleep_by_date[row.get("date")] = float(row["sleep_duration_hours"])

        # Get sleep values for dates where we have energy data
        matching_sleep = []
        for energy_row in energy_rows:
            d = energy_row.get("date")
            if d in sleep_by_date:
                matching_sleep.append(sleep_by_date[d])

        return sum(matching_sleep) / len(matching_sleep) if matching_sleep else None

    # =========================================================================
    # Check-in Pattern Analyzers
    # =========================================================================

    async def _analyze_mood_patterns(self, user_id: str, metrics_data: List[Dict]) -> Optional[Dict]:
        """Analyze mood patterns from check-in data."""
        mood_rows = [r for r in metrics_data if r.get("avg_mood") is not None]
        if len(mood_rows) < 2:
            return None

        mood_values = [float(r["avg_mood"]) for r in mood_rows]
        avg_mood = sum(mood_values) / len(mood_values)
        mood_std = pstdev(mood_values) if len(mood_values) > 1 else 0

        # Analyze weekday vs weekend mood
        weekday_avg, weekend_avg = self._weekday_weekend_avgs(mood_rows, "avg_mood")

        # Analyze day-of-week patterns (find low days)
        dow_avgs = self._day_of_week_avgs(mood_rows, "avg_mood")
        worst_day, worst_avg = min(dow_avgs.items(), key=lambda x: x[1]) if dow_avgs else (None, None)
        best_day, best_avg = max(dow_avgs.items(), key=lambda x: x[1]) if dow_avgs else (None, None)

        # Calculate trend (last 3 days vs first 3 days)
        trend = self._calculate_trend(mood_values)

        pattern_strength = min(1.0, mood_std / 1.0)  # Higher variance = stronger pattern
        confidence = self._confidence(len(mood_rows), max(0.3, pattern_strength))

        labels, values = self._last_7_days_series(mood_rows, "avg_mood")
        highlight_index = self._highlight_min_index(values)

        # Generate insight based on patterns
        if avg_mood < 2.5:
            insight_type = InsightType.RISK
            commentary = f"Your mood has been low lately, averaging {avg_mood:.1f}/5. Let's talk about what's going on."
            action_steps = [
                "Try 10 minutes of sunlight within an hour of waking",
                "Move your body for 20 minutes today - even a walk counts",
                "Reach out to someone you trust and tell them how you're feeling",
            ]
        elif worst_day and worst_avg and best_avg and (best_avg - worst_avg) > 0.8:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your mood dips on {worst_day}s ({worst_avg:.1f}/5) compared to {best_day}s ({best_avg:.1f}/5). What's different about those days?"
            action_steps = [
                f"Plan something enjoyable for {worst_day}s - even small rewards help",
                f"Notice what's draining you on {worst_day}s vs energizing you on {best_day}s",
                "Consider if work or obligations cluster on your low days",
            ]
        elif trend < -0.3:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your mood has been trending down this week. Time to intervene before it spirals."
            action_steps = [
                "Pick one thing that usually lifts your mood and do it today",
                "Get to bed 30 minutes earlier tonight",
                "Reduce news and social media for the next 48 hours",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"Your mood is holding steady around {avg_mood:.1f}/5. Keep doing what you're doing."
            action_steps = [
                "Notice what's working and keep it in your routine",
                "Small wins compound - celebrate consistency",
            ]

        trend_direction = "down" if trend < -0.2 else "up" if trend > 0.2 else "stable"
        trend_value = f"{avg_mood:.1f}/5 avg"

        insight = HealthInsight(
            id=f"mood-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Your Mood Pattern",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.MOOD_PATTERN,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction=trend_direction,
                trend_value=trend_value,
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.MOOD_PATTERN.value,
            confidence=confidence,
            pattern_data={
                "avg_mood": round(avg_mood, 2),
                "mood_std": round(mood_std, 2),
                "weekday_avg": weekday_avg,
                "weekend_avg": weekend_avg,
                "worst_day": worst_day,
                "trend": round(trend, 2),
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_checkin_energy_patterns(
        self, user_id: str, metrics_data: List[Dict], health_data: List[Dict]
    ) -> Optional[Dict]:
        """Analyze energy patterns from check-ins, correlating with sleep when available."""
        energy_rows = [r for r in metrics_data if r.get("avg_energy") is not None]
        if len(energy_rows) < 2:
            return None

        energy_values = [float(r["avg_energy"]) for r in energy_rows]
        avg_energy = sum(energy_values) / len(energy_values)
        energy_std = pstdev(energy_values) if len(energy_values) > 1 else 0

        # Build sleep correlation if we have matching health data
        sleep_correlation = self._correlate_with_sleep(energy_rows, health_data)

        # Analyze day-of-week patterns
        dow_avgs = self._day_of_week_avgs(energy_rows, "avg_energy")
        worst_day, worst_avg = min(dow_avgs.items(), key=lambda x: x[1]) if dow_avgs else (None, None)
        best_day, best_avg = max(dow_avgs.items(), key=lambda x: x[1]) if dow_avgs else (None, None)

        trend = self._calculate_trend(energy_values)

        pattern_strength = min(1.0, energy_std / 1.0)
        confidence = self._confidence(len(energy_rows), max(0.3, pattern_strength))

        labels, values = self._last_7_days_series(energy_rows, "avg_energy")
        highlight_index = self._highlight_min_index(values)

        # Generate insight based on patterns
        if avg_energy < 2.5:
            insight_type = InsightType.RISK
            if sleep_correlation and sleep_correlation < 6.5:
                commentary = f"Your energy is low ({avg_energy:.1f}/5) and your sleep averaging {sleep_correlation:.1f}h might be why."
                action_steps = [
                    "Get 7+ hours tonight - make it non-negotiable",
                    "Cut caffeine after 2 PM",
                    "Consider a 20-minute power nap between 1-3 PM",
                ]
            else:
                commentary = f"Your energy has been dragging at {avg_energy:.1f}/5. Something's draining your battery."
                action_steps = [
                    "Hydrate - dehydration tanks energy. Aim for 8 glasses today",
                    "Get outside for 15 minutes - natural light resets your system",
                    "Check if you're eating enough protein and complex carbs",
                ]
        elif worst_day and best_day and best_avg and worst_avg and (best_avg - worst_avg) > 0.8:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your energy tanks on {worst_day}s ({worst_avg:.1f}/5). {best_day}s are your power days ({best_avg:.1f}/5)."
            action_steps = [
                f"Schedule demanding tasks on {best_day}s when possible",
                f"Protect {worst_day}s - lighter work, no major decisions",
                "Track what you eat/drink on low days vs high days",
            ]
        elif trend < -0.3:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your energy is on a downward slide. Time to troubleshoot before you hit empty."
            action_steps = [
                "Audit your sleep this week - are you actually resting?",
                "Look for energy vampires: stress, poor food, dehydration",
                "Try a 10-minute walk after lunch today",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"Your energy is stable at {avg_energy:.1f}/5. You're managing your battery well."
            action_steps = [
                "Keep tracking - you're building self-awareness",
                "Note what boosts your energy so you can replicate it",
            ]

        trend_direction = "down" if trend < -0.2 else "up" if trend > 0.2 else "stable"
        trend_value = f"{avg_energy:.1f}/5 avg"

        insight = HealthInsight(
            id=f"checkin-energy-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Your Energy Levels",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.CHECKIN_ENERGY_PATTERN,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction=trend_direction,
                trend_value=trend_value,
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.CHECKIN_ENERGY_PATTERN.value,
            confidence=confidence,
            pattern_data={
                "avg_energy": round(avg_energy, 2),
                "energy_std": round(energy_std, 2),
                "worst_day": worst_day,
                "best_day": best_day,
                "sleep_correlation": round(sleep_correlation, 2) if sleep_correlation else None,
                "trend": round(trend, 2),
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_stress_patterns(self, user_id: str, metrics_data: List[Dict]) -> Optional[Dict]:
        """Analyze stress patterns from check-in data."""
        stress_rows = [r for r in metrics_data if r.get("avg_stress") is not None]
        if len(stress_rows) < 2:
            return None

        stress_values = [float(r["avg_stress"]) for r in stress_rows]
        avg_stress = sum(stress_values) / len(stress_values)
        stress_std = pstdev(stress_values) if len(stress_values) > 1 else 0

        # Analyze weekday vs weekend stress
        weekday_avg, weekend_avg = self._weekday_weekend_avgs(stress_rows, "avg_stress")

        # Analyze day-of-week patterns (find high stress days)
        dow_avgs = self._day_of_week_avgs(stress_rows, "avg_stress")
        worst_day, worst_avg = max(dow_avgs.items(), key=lambda x: x[1]) if dow_avgs else (None, None)
        best_day, best_avg = min(dow_avgs.items(), key=lambda x: x[1]) if dow_avgs else (None, None)

        trend = self._calculate_trend(stress_values)

        pattern_strength = min(1.0, avg_stress / 3.0)  # Higher stress = stronger pattern
        confidence = self._confidence(len(stress_rows), max(0.3, pattern_strength))

        labels, values = self._last_7_days_series(stress_rows, "avg_stress")
        highlight_index = self._highlight_max_index(values)  # Highlight highest stress day

        # Generate insight based on patterns
        if avg_stress > 3.5:
            insight_type = InsightType.RISK
            commentary = f"Your stress is running hot at {avg_stress:.1f}/5. That's not sustainable."
            action_steps = [
                "Take 5 minutes right now to do box breathing (4-4-4-4)",
                "Write down the top 3 things stressing you - get them out of your head",
                "Say no to one thing today. Just one.",
            ]
        elif weekday_avg and weekend_avg and weekday_avg > weekend_avg + 0.5:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Weekdays stress you out ({weekday_avg:.1f}/5) way more than weekends ({weekend_avg:.1f}/5). Work is the culprit."
            action_steps = [
                "Build a 10-minute decompression ritual for end of workday",
                "Block 'focus time' on your calendar to reduce meeting overwhelm",
                "Start Monday with your hardest task - don't let it loom all week",
            ]
        elif worst_day and worst_avg and best_avg and (worst_avg - best_avg) > 1.0:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Stress spikes on {worst_day}s ({worst_avg:.1f}/5). What's happening that day?"
            action_steps = [
                f"Look at your {worst_day} schedule - what's triggering the spike?",
                f"Add one stress-relief activity to {worst_day}s (walk, music, call a friend)",
                "Consider moving stressful tasks off your already-hard day",
            ]
        elif trend > 0.3:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your stress is creeping up. Let's get ahead of this before it snowballs."
            action_steps = [
                "Identify the new stressor that's entered your life",
                "Move your body - exercise is the #1 stress reducer",
                "Talk to someone about what's weighing on you",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"Your stress is manageable at {avg_stress:.1f}/5. You're handling things."
            action_steps = [
                "Keep using whatever coping strategies are working",
                "Build up your stress tolerance with regular exercise",
            ]

        trend_direction = "up" if trend > 0.2 else "down" if trend < -0.2 else "stable"
        trend_value = f"{avg_stress:.1f}/5 avg"

        insight = HealthInsight(
            id=f"stress-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Your Stress Levels",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.STRESS_PATTERN,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction=trend_direction,
                trend_value=trend_value,
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.STRESS_PATTERN.value,
            confidence=confidence,
            pattern_data={
                "avg_stress": round(avg_stress, 2),
                "stress_std": round(stress_std, 2),
                "weekday_avg": weekday_avg,
                "weekend_avg": weekend_avg,
                "worst_day": worst_day,
                "trend": round(trend, 2),
            },
            insight_title=insight.title,
        )

        return {"insight": insight, "confidence": confidence}


health_insights_engine = HealthInsightsEngine()
