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


MIN_DAYS_FOR_INSIGHTS = 7
MAX_DAYS = 14


class HealthInsightsEngine:
    def __init__(self):
        self.supabase = get_supabase_client()

    async def get_active_insights(self, user_id: str) -> Dict:
        try:
            health_data = await self._fetch_user_health_data(user_id, days=MAX_DAYS)
            days_with_data = self._count_days_with_data(health_data)

            if days_with_data < MIN_DAYS_FOR_INSIGHTS:
                return {
                    "coach_summary": None,
                    "patterns": [],
                    "has_enough_data": False,
                    "days_until_enough_data": max(1, MIN_DAYS_FOR_INSIGHTS - days_with_data),
                }

            results = await asyncio.gather(
                self._analyze_sleep_patterns(user_id, health_data),
                self._analyze_energy_windows(user_id, health_data),
                self._analyze_activity_consistency(user_id, health_data),
                self._analyze_weekend_effect(user_id, health_data),
                return_exceptions=True,
            )

            insights: List[HealthInsight] = []
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Health pattern detection failed: {result}")
                    continue
                if result is not None and result["confidence"] >= 0.4:
                    insights.append(result["insight"])

            type_priority = {
                InsightType.RISK: 0,
                InsightType.BEHAVIORAL: 1,
                InsightType.PROGRESS: 2,
            }
            insights.sort(key=lambda x: type_priority.get(x.type, 99))
            insights = insights[:5]

            has_risk = any(i.type == InsightType.RISK for i in insights)
            coach_summary = (
                f"Looked at your health data from the last week. "
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
            start_date = (date.today() - timedelta(days=days - 1)).isoformat()

            # Query the aggregation view with all fields including sleep times
            response = (
                self.supabase.table("health_metrics_daily")
                .select(
                    "date,sleep_duration_hours,sleep_start_hour,sleep_end_hour,"
                    "sleep_start_time,sleep_end_time,steps,active_energy,"
                    "avg_heart_rate,resting_heart_rate,data_completeness"
                )
                .eq("user_id", user_id)
                .gte("date", start_date)
                .order("date")
                .execute()
            )
            data = response.data or []

            if data:
                # Add null fields for compatibility with pattern analysis methods
                for row in data:
                    row["hourly_activity"] = None
                    row["active_minutes"] = None
                    row["exercise_minutes"] = None
                    row["sedentary_minutes"] = None
                return data

            # Fallback: aggregate raw health_metrics if view query fails
            return self._aggregate_health_metrics(user_id, start_date)
        except Exception as e:
            logger.error(f"Error fetching health data: {e}")
            # Fallback to direct aggregation
            start_date = (date.today() - timedelta(days=days - 1)).isoformat()
            return self._aggregate_health_metrics(user_id, start_date)

    def _aggregate_health_metrics(self, user_id: str, start_date: str) -> List[Dict]:
        """Fallback aggregation when database view is not available."""
        try:
            response = (
                self.supabase.table("health_metrics")
                .select("metric_type,value,recorded_at")
                .eq("user_id", user_id)
                .gte("recorded_at", start_date)
                .execute()
            )
            rows = response.data or []
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
        if len(sleep_rows) < 4:
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
        elif avg_sleep < 7.2:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"You're averaging {avg_sleep:.1f} hours. You're flirting with sleep debt."
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"You're averaging {avg_sleep:.1f} hours. That's a solid base to build on."

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
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_energy_windows(self, user_id: str, health_data: List[Dict]) -> Optional[Dict]:
        """Analyze energy windows using sleep schedule (bedtime/wake time) data."""
        sleep_rows = [
            r for r in health_data
            if r.get("sleep_start_hour") is not None and r.get("sleep_end_hour") is not None
        ]

        if len(sleep_rows) < 4:
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
        elif is_night_person:
            commentary = f"You're a night owl. Most active after 8pm. Stop pretending mornings work."
            insight_type = InsightType.BEHAVIORAL
            peak_window = f"8pm-{bed_label}"
        else:
            midpoint = (avg_wake + avg_bedtime) / 2
            peak_start = int(midpoint - 1.5) % 24
            peak_window = self._format_hour_window(peak_start, 3)
            commentary = f"Your energy peaks {peak_window}. Use that window for hard tasks."
            insight_type = InsightType.BEHAVIORAL

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
        )

        return {"insight": insight, "confidence": confidence}

    async def _analyze_activity_consistency(
        self, user_id: str, health_data: List[Dict]
    ) -> Optional[Dict]:
        step_rows = [r for r in health_data if r.get("steps") is not None and float(r["steps"]) > 0]
        if len(step_rows) < 4:
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
        elif cv >= 0.35:
            commentary = (
                f"Averaging {int(avg_steps):,} steps but with big swings. "
                f"Build a daily floor you can hit consistently."
            )
            insight_type = InsightType.BEHAVIORAL
        else:
            commentary = (
                f"Averaging {int(avg_steps):,} steps with steady consistency. "
                f"That's a solid movement habit."
            )
            insight_type = InsightType.PROGRESS

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

        if parts:
            commentary = f"Weekend {', '.join(parts)}. It throws off your week."
            insight_type = InsightType.RISK
        else:
            commentary = "Your weekends look steady. Keep the rhythm consistent."
            insight_type = InsightType.PROGRESS

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
    ) -> None:
        try:
            self.supabase.table("user_health_patterns").upsert(
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


health_insights_engine = HealthInsightsEngine()
