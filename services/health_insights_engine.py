"""
Health Insights Engine
Analyzes health-first patterns (sleep, activity, energy windows, consistency)
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
    CONSISTENCY = "consistency"
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
    @property
    def supabase(self):
        """Get the current Supabase client (always fresh after a reset)."""
        return get_supabase_client()

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
                self._analyze_sleep_patterns(user_id, health_data, metrics_data),
                self._analyze_energy_windows(user_id, health_data),
                self._analyze_activity_consistency(user_id, health_data),
                self._analyze_consistency(user_id, health_data),
                # Check-in based analyzers
                self._analyze_mood_patterns(user_id, metrics_data),
                self._analyze_checkin_energy_patterns(user_id, metrics_data, health_data),
                self._analyze_stress_patterns(user_id, metrics_data),
                return_exceptions=True,
            )

            pattern_names = [
                "sleep", "energy_windows", "activity", "consistency",
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

            pattern_order = {
                PatternType.SLEEP_PATTERN: 0,
                PatternType.ACTIVITY_CONSISTENCY: 1,
                PatternType.ENERGY_WINDOWS: 2,
                PatternType.MOOD_PATTERN: 3,
                PatternType.CHECKIN_ENERGY_PATTERN: 4,
                PatternType.STRESS_PATTERN: 5,
                PatternType.CONSISTENCY: 6,
            }
            insights.sort(key=lambda x: pattern_order.get(x.evidence.type, 99))

            has_risk = any(i.type == InsightType.RISK for i in insights)
            count = len(insights)

            if not insights:
                coach_summary = None
            elif count == 1 and has_risk:
                coach_summary = "Went through your data from this week. One thing stood out that you should look at."
            elif count == 1:
                coach_summary = "Had a look at your week. Spotted something worth knowing about."
            elif has_risk:
                coach_summary = f"Checked your data from the past week. {count} patterns came up and a couple need your attention."
            else:
                coach_summary = f"Looked through your week. Found {count} things worth flagging, nothing mad though."

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
                .limit(365)
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
                .limit(5000)
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

    async def _analyze_sleep_patterns(
        self, user_id: str, health_data: List[Dict], metrics_data: List[Dict] = None
    ) -> Optional[Dict]:
        # Build a merged dataset: start with health_data, fill zero-sleep days from check-in data
        checkin_sleep_by_date: Dict[str, float] = {}
        if metrics_data:
            for m_row in metrics_data:
                if m_row.get("avg_sleep_hours") is not None and float(m_row["avg_sleep_hours"]) > 0:
                    checkin_sleep_by_date[m_row["date"]] = float(m_row["avg_sleep_hours"])

        logger.info(f"[SleepAnalysis] health_data rows: {len(health_data)}, checkin_sleep dates: {list(checkin_sleep_by_date.keys())}")

        # Merge: replace zero/missing HealthKit sleep with check-in values
        merged_data = []
        for r in health_data:
            d = r.get("date")
            hk_sleep = float(r.get("sleep_duration_hours") or 0)
            if hk_sleep == 0 and d in checkin_sleep_by_date:
                merged_row = dict(r)
                merged_row["sleep_duration_hours"] = checkin_sleep_by_date[d]
                merged_data.append(merged_row)
            else:
                merged_data.append(r)

        # Also add check-in dates not present in health_data at all
        health_data_dates = {r.get("date") for r in health_data}
        for d, val in checkin_sleep_by_date.items():
            if d not in health_data_dates:
                merged_data.append({
                    "date": d,
                    "sleep_duration_hours": val,
                    "sleep_start_hour": None,
                    "sleep_end_hour": None,
                    "steps": None,
                })
        merged_data.sort(key=lambda x: x.get("date", ""))

        # Filter to rows with actual sleep values for analysis
        sleep_rows = [r for r in merged_data if float(r.get("sleep_duration_hours") or 0) > 0]

        logger.info(f"[SleepAnalysis] After merge: {len(merged_data)} total rows, {len(sleep_rows)} with sleep > 0")

        if len(sleep_rows) < 2:
            logger.info(f"[SleepAnalysis] Not enough sleep data ({len(sleep_rows)} rows), skipping")
            return None

        sleep_values = [float(r["sleep_duration_hours"]) for r in sleep_rows]
        avg_sleep = sum(sleep_values) / len(sleep_values)
        sleep_std = pstdev(sleep_values) if len(sleep_values) > 1 else 0

        weekday_avg, weekend_avg = self._weekday_weekend_avgs(sleep_rows, "sleep_duration_hours")

        # Floor at 0.4 so the card still shows when sleep is near 7h (healthy)
        pattern_strength = max(0.4, min(1.0, abs(avg_sleep - 7.0) / 2.0))
        confidence = self._confidence(len(sleep_rows), pattern_strength)

        logger.info(f"[SleepAnalysis] avg={avg_sleep:.1f}h, strength={pattern_strength:.2f}, confidence={confidence:.2f}, rows={len(sleep_rows)}")

        # Use merged data for the chart so check-in values appear instead of zeros
        labels, values = self._last_7_days_series(merged_data, "sleep_duration_hours")

        highlight_index = self._highlight_min_index(values)

        # Find worst night for specificity
        worst_value = min(sleep_values)
        worst_idx = sleep_values.index(worst_value)
        worst_date = self._parse_date(sleep_rows[worst_idx].get("date"))
        worst_day_name = worst_date.strftime("%A") if worst_date else None

        # Calculate trend
        trend = self._calculate_trend(sleep_values)

        if avg_sleep < 6.5:
            insight_type = InsightType.RISK
            worst_note = f" {worst_day_name} was your lowest at {worst_value:.1f}h." if worst_day_name else ""
            if trend < -0.3:
                commentary = (
                    f"You're clocking {avg_sleep:.1f} hours and it's getting worse.{worst_note} "
                    f"Sleep debt stacks up proper quick."
                )
            else:
                commentary = (
                    f"Only getting {avg_sleep:.1f} hours on average, that's under the 7h mark.{worst_note}"
                )
            action_steps = [
                "Set a hard bedtime alarm 8 hours before your wake time",
                "No screens 30 minutes before bed",
                "If you can, grab a 20 min power nap between 1 and 3 PM",
            ]
        elif avg_sleep < 7.2:
            insight_type = InsightType.BEHAVIORAL
            regularity_note = f" Your sleep varied by about {sleep_std:.1f}h night to night." if sleep_std > 0.5 else ""
            commentary = (
                f"Sitting at {avg_sleep:.1f} hours, right on the edge of sleep debt.{regularity_note}"
            )
            action_steps = [
                "Move your bedtime back by 15 minutes this week",
                "Reduce caffeine after 2 PM",
                "Track what keeps you up. Phone, racing thoughts, or environment",
            ]
        else:
            insight_type = InsightType.PROGRESS
            if trend > 0.3:
                commentary = f"Clocking {avg_sleep:.1f} hours and it's getting better. Sleep is moving in the right direction."
            else:
                commentary = f"Getting {avg_sleep:.1f} hours with {sleep_std:.1f}h variation. Solid foundation that."
            action_steps = [
                "Keep your sleep schedule consistent from one day to the next",
                "Notice how your sleep affects energy and focus the next day",
            ]

        trend_direction = "down" if trend < -0.2 else "up" if trend > 0.2 else "stable"
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
                "used_checkin_fallback": bool(checkin_sleep_by_date),
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

        # Normalize bedtimes: hours 0-6 are post-midnight, treat as 24-30
        raw_bedtimes = [float(r["sleep_start_hour"]) for r in sleep_rows]
        normalized_bedtimes = [h + 24 if h <= 6 else h for h in raw_bedtimes]
        wake_times = [float(r["sleep_end_hour"]) for r in sleep_rows]

        avg_bedtime_norm = sum(normalized_bedtimes) / len(normalized_bedtimes)
        avg_bedtime = avg_bedtime_norm % 24
        avg_wake = sum(wake_times) / len(wake_times)

        # Classify based on normalized bedtime (handles overnight sleep)
        is_night_owl = avg_bedtime_norm >= 23
        is_morning_person = avg_bedtime_norm < 23 and avg_wake < 8

        # Pattern strength based on schedule consistency
        bedtime_std = pstdev(normalized_bedtimes) if len(normalized_bedtimes) > 1 else 0
        wake_std = pstdev(wake_times) if len(wake_times) > 1 else 0
        consistency = max(0.0, 1.0 - (bedtime_std + wake_std) / 4.0)
        pattern_strength = max(0.3, consistency)
        confidence = self._confidence(len(sleep_rows), pattern_strength)

        wake_label = self._hour_label(int(avg_wake) % 24)
        bed_label = self._hour_label(int(avg_bedtime) % 24)

        # Productive window: wake + 1h to wake + 4h (cortisol peak)
        peak_start = (int(avg_wake) + 1) % 24
        peak_end = (int(avg_wake) + 4) % 24
        peak_window = f"{self._hour_label(peak_start)} to {self._hour_label(peak_end)}"

        if is_morning_person:
            commentary = (
                f"You're up early, {wake_label} rise, {bed_label} lights out. "
                f"Get the hard stuff done in {peak_window}."
            )
            insight_type = InsightType.PROGRESS
            action_steps = [
                f"Block {peak_window} for deep work",
                "Protect mornings from meetings when possible",
                "Use afternoon for admin and routine tasks",
            ]
        elif is_night_owl:
            commentary = (
                f"You're on a late schedule, up around {wake_label}, crashing around {bed_label}. "
                f"Your sharpest window is {peak_window}."
            )
            insight_type = InsightType.BEHAVIORAL
            action_steps = [
                f"Block {peak_window} for deep or creative work",
                "Use the first hour after waking for routine tasks, not decisions",
                "Protect your sleep. Consistency matters more than waking up early",
            ]
        else:
            commentary = (
                f"Up around {wake_label}, out by {bed_label}. "
                f"{peak_window} is when you're sharpest."
            )
            insight_type = InsightType.BEHAVIORAL
            action_steps = [
                f"Block {peak_window} for your hardest task of the day",
                "Use the hour after lunch for routine work, not deep thinking",
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
                "is_night_owl": is_night_owl,
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

        # Find best/worst days
        best_idx = step_values.index(max_steps)
        worst_idx = step_values.index(min_steps)
        best_date = self._parse_date(step_rows[best_idx].get("date"))
        worst_date = self._parse_date(step_rows[worst_idx].get("date"))
        best_day = best_date.strftime("%A") if best_date else None
        worst_day = worst_date.strftime("%A") if worst_date else None

        # Pattern strength: any clear activity pattern is interesting
        # High CV = inconsistent (risk insight), Low CV = consistent (progress insight)
        pattern_strength = max(0.5, min(1.0, cv / 0.5)) if cv >= 0.3 else max(0.5, 1.0 - cv)
        confidence = self._confidence(len(step_rows), pattern_strength)

        labels, values = self._last_7_days_series(health_data, "steps")
        highlight_index = self._highlight_max_index(values)

        if cv >= 0.6:
            day_context = ""
            if best_day and worst_day:
                day_context = f" {best_day} hit {int(max_steps):,}, {worst_day} dropped to {int(min_steps):,}."
            commentary = (
                f"Your movement is all over the shop.{day_context} "
                f"Being consistent matters way more than big days."
            )
            insight_type = InsightType.RISK
            action_steps = [
                f"Set a minimum daily floor of {int(min_steps + (avg_steps - min_steps) * 0.3):,} steps",
                "On quiet days, take a 15 min walk after lunch",
                "Track what kills your movement on zero days",
            ]
        elif cv >= 0.35:
            commentary = (
                f"Doing about {int(avg_steps):,} steps but swinging between "
                f"{int(min_steps):,} and {int(max_steps):,}. "
                f"A steady daily minimum does more than smashing it once."
            )
            insight_type = InsightType.BEHAVIORAL
            action_steps = [
                f"Aim for at least {int(avg_steps * 0.8):,} steps every day this week",
                "Schedule movement at the same time each day to build habit",
            ]
        else:
            best_note = f" {best_day} was your strongest at {int(max_steps):,}." if best_day else ""
            commentary = (
                f"Putting in about {int(avg_steps):,} steps and staying proper consistent.{best_note}"
            )
            insight_type = InsightType.PROGRESS
            action_steps = [
                f"You're consistent, try bumping your target to {int(avg_steps * 1.1):,} steps",
                "Add one 20 min walk on your best energy day",
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

    async def _analyze_consistency(self, user_id: str, health_data: List[Dict]) -> Optional[Dict]:
        """Analyze day-to-day consistency of sleep timing and activity across all 7 days.
        Only surfaces when variance is notable — returns None for consistent users."""
        sleep_timing_rows = [
            r for r in health_data
            if r.get("sleep_start_hour") is not None
        ]
        step_rows = [
            r for r in health_data
            if r.get("steps") is not None and float(r["steps"]) > 0
        ]

        has_sleep = len(sleep_timing_rows) >= 3
        has_steps = len(step_rows) >= 3

        if not has_sleep and not has_steps:
            return None

        sleep_std = 0.0
        step_cv = 0.0
        inconsistent_metrics = []

        if has_sleep:
            bedtimes = [float(r["sleep_start_hour"]) for r in sleep_timing_rows]
            sleep_std = pstdev(bedtimes) if len(bedtimes) > 1 else 0.0
            if sleep_std > 1.5:
                inconsistent_metrics.append("sleep timing")

        if has_steps:
            steps = [float(r["steps"]) for r in step_rows]
            avg_steps = sum(steps) / len(steps)
            step_std = pstdev(steps) if len(steps) > 1 else 0.0
            step_cv = step_std / avg_steps if avg_steps > 0 else 0.0
            if step_cv > 0.5:
                inconsistent_metrics.append("activity")

        # Only surface when there's actually notable inconsistency
        if not inconsistent_metrics:
            return None

        # Pattern strength scales with how far above threshold
        max_deviation = max(
            sleep_std / 1.5 if has_sleep else 0,
            step_cv / 0.5 if has_steps else 0,
        )
        pattern_strength = min(1.0, max(0.4, max_deviation - 1.0 + 0.4))
        sample_size = max(len(sleep_timing_rows), len(step_rows))
        confidence = self._confidence(sample_size, pattern_strength)

        # Build commentary
        parts = []
        if "sleep timing" in inconsistent_metrics:
            parts.append(f"bedtime varied by {sleep_std:.1f} hours")
        if "activity" in inconsistent_metrics:
            min_s = int(min(steps))
            max_s = int(max(steps))
            parts.append(f"steps ranged from {min_s:,} to {max_s:,}")

        if len(inconsistent_metrics) > 1:
            insight_type = InsightType.RISK
            commentary = (
                f"Your week was all over the gaff, {' and '.join(parts)}. "
                f"When nothing's consistent it catches up to you."
            )
            action_steps = [
                "Pick a fixed wake time and stick to it every day this week",
                "Set a daily step floor you can hit even on rest days",
                "Consistent routines reduce decision fatigue",
            ]
        else:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your {inconsistent_metrics[0]} was a bit all over it this week, {parts[0]}."
            if "sleep timing" in inconsistent_metrics:
                action_steps = [
                    "Try keeping your bedtime within one hour each night",
                    "A consistent sleep schedule helps your body clock",
                ]
            else:
                action_steps = [
                    "Set a daily step minimum rather than relying on big days",
                    "Short walks on rest days keep your baseline steady",
                ]

        # Use the most inconsistent metric for the chart
        if "sleep timing" in inconsistent_metrics and has_sleep:
            labels, values = self._last_7_days_series(health_data, "sleep_start_hour")
            highlight_index = self._highlight_max_index(values)
            trend_value = f"{sleep_std:.1f}h variation"
        else:
            labels, values = self._last_7_days_series(health_data, "steps")
            highlight_index = self._highlight_min_index(values)
            trend_value = f"CV {step_cv:.2f}"

        insight = HealthInsight(
            id=f"consistency-{user_id}-{datetime.utcnow().isoformat()}",
            type=insight_type,
            title="Weekly Consistency",
            coach_commentary=commentary,
            evidence=PatternEvidence(
                type=PatternType.CONSISTENCY,
                labels=labels,
                values=values,
                highlight_index=highlight_index,
                trend_direction="down" if len(inconsistent_metrics) > 1 else "stable",
                trend_value=trend_value,
            ),
            action_text="Ask Coach",
            is_new=True,
            created_at=datetime.utcnow(),
            action_steps=action_steps,
        )

        self._upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.CONSISTENCY.value,
            confidence=confidence,
            pattern_data={
                "sleep_timing_std": round(sleep_std, 2) if has_sleep else None,
                "step_cv": round(step_cv, 2) if has_steps else None,
                "inconsistent_metrics": inconsistent_metrics,
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
        # Always anchor to today so the chart shows the most recent 7 days
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
        return f"{self._hour_label(start_hour)} to {self._hour_label(end_hour)}"

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
        """Fetch daily check-in data (mood, energy, stress, sleep) from user_metrics table."""
        try:
            from datetime import timezone as tz
            today_utc = datetime.now(tz.utc).date()
            start_date = (today_utc - timedelta(days=days - 1)).isoformat()

            logger.info(f"[HealthInsights] Fetching user_metrics for user {user_id}, start_date={start_date}")

            response = (
                self.supabase.table("user_metrics")
                .select("metric_type,value,logged_at,context")
                .eq("user_id", user_id)
                .in_("metric_type", ["mood", "energy", "stress", "sleep"])
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
                    "sleep_values": [],
                }

            metric_type = row.get("metric_type")
            value = float(row.get("value", 0))

            if metric_type == "mood":
                daily[day]["mood_values"].append(value)
            elif metric_type == "energy":
                daily[day]["energy_values"].append(value)
            elif metric_type == "stress":
                daily[day]["stress_values"].append(value)
            elif metric_type == "sleep":
                daily[day]["sleep_values"].append(value)

        # Calculate daily averages
        result = []
        for day in sorted(daily.keys()):
            d = daily[day]
            result.append({
                "date": day,
                "avg_mood": sum(d["mood_values"]) / len(d["mood_values"]) if d["mood_values"] else None,
                "avg_energy": sum(d["energy_values"]) / len(d["energy_values"]) if d["energy_values"] else None,
                "avg_stress": sum(d["stress_values"]) / len(d["stress_values"]) if d["stress_values"] else None,
                "avg_sleep_hours": sum(d["sleep_values"]) / len(d["sleep_values"]) if d["sleep_values"] else None,
                "mood_count": len(d["mood_values"]),
                "energy_count": len(d["energy_values"]),
                "stress_count": len(d["stress_values"]),
                "sleep_count": len(d["sleep_values"]),
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
            commentary = f"Your mood's been low lately, sitting at {avg_mood:.1f}/5. Let's chat about what's going on."
            action_steps = [
                "Try 10 minutes of sunlight within an hour of waking",
                "Move your body for 20 minutes today, even a walk counts",
                "Reach out to someone you trust and tell them how you're feeling",
            ]
        elif worst_day and worst_avg and best_avg and (best_avg - worst_avg) > 0.8:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your mood drops on {worst_day}s ({worst_avg:.1f}/5) but picks up on {best_day}s ({best_avg:.1f}/5). What's different about those days?"
            action_steps = [
                f"Plan something enjoyable for {worst_day}s, even small rewards help",
                f"Notice what's draining you on {worst_day}s vs energizing you on {best_day}s",
                "Consider if work or obligations cluster on your low days",
            ]
        elif trend < -0.3:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your mood's been sliding this week. Worth doing something about it before it gets worse."
            action_steps = [
                "Pick one thing that usually lifts your mood and do it today",
                "Get to bed 30 minutes earlier tonight",
                "Reduce news and social media for the next 48 hours",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"Your mood's been steady around {avg_mood:.1f}/5. Whatever you're doing, keep at it."
            action_steps = [
                "Notice what's working and keep it in your routine",
                "Small wins compound, celebrate consistency",
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
                commentary = f"Your energy's proper low at {avg_energy:.1f}/5 and averaging {sleep_correlation:.1f}h of sleep is probably why."
                action_steps = [
                    "Get 7+ hours tonight, no excuses",
                    "Cut caffeine after 2 PM",
                    "Try a 20 min power nap between 1 and 3 PM",
                ]
            else:
                commentary = f"Your energy's been dragging at {avg_energy:.1f}/5. Something's draining you."
                action_steps = [
                    "Hydrate, dehydration tanks energy. Aim for 8 glasses today",
                    "Get outside for 15 minutes, natural light resets your system",
                    "Check if you're eating enough protein and complex carbs",
                ]
        elif worst_day and best_day and best_avg and worst_avg and (best_avg - worst_avg) > 0.8:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your energy tanks on {worst_day}s ({worst_avg:.1f}/5). {best_day}s are when you're buzzing ({best_avg:.1f}/5)."
            action_steps = [
                f"Schedule demanding tasks on {best_day}s when possible",
                f"Protect {worst_day}s, lighter work, no major decisions",
                "Track what you eat and drink on low days vs high days",
            ]
        elif trend < -0.3:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your energy's been dropping off. Worth sorting it before you hit empty."
            action_steps = [
                "Audit your sleep this week, are you actually resting?",
                "Look for energy vampires: stress, poor food, dehydration",
                "Try a 10 min walk after lunch today",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"Your energy's steady at {avg_energy:.1f}/5. You're managing it well."
            action_steps = [
                "Keep tracking, you're building proper awareness",
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
            commentary = f"Your stress is mad high at {avg_stress:.1f}/5. That's not gonna last."
            action_steps = [
                "Take 5 minutes right now to do box breathing (4 seconds each)",
                "Write down the top 3 things stressing you, get them out of your head",
                "Say no to one thing today. Just one.",
            ]
        elif weekday_avg and weekend_avg and weekday_avg > weekend_avg + 0.5:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Weekdays are stressing you out ({weekday_avg:.1f}/5) way more than weekends ({weekend_avg:.1f}/5). Work's the one doing it."
            action_steps = [
                "Build a 10 min wind down ritual for end of workday",
                "Block 'focus time' on your calendar to reduce meeting overwhelm",
                "Start Monday with your hardest task, don't let it loom all week",
            ]
        elif worst_day and worst_avg and best_avg and (worst_avg - best_avg) > 1.0:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Stress spikes on {worst_day}s ({worst_avg:.1f}/5). What's going on that day?"
            action_steps = [
                f"Look at your {worst_day} schedule, what's triggering the spike?",
                f"Add one thing that calms you down to {worst_day}s (walk, music, call a friend)",
                "Consider moving stressful tasks off your toughest day",
            ]
        elif trend > 0.3:
            insight_type = InsightType.BEHAVIORAL
            commentary = f"Your stress is creeping up. Best to get on top of it before it gets out of hand."
            action_steps = [
                "Identify the new stressor that's entered your life",
                "Move your body, exercise is the number one stress reducer",
                "Talk to someone about what's weighing on you",
            ]
        else:
            insight_type = InsightType.PROGRESS
            commentary = f"Your stress is calm at {avg_stress:.1f}/5. You're handling it."
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
