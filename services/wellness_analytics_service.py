"""
Wellness Analytics Service
Calculates wellness scores and analyzes health trends
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from backend.database.supabase_client import get_supabase_client
from backend.utils.supabase_utils import extract_supabase_data

logger = logging.getLogger(__name__)


@dataclass
class WellnessScore:
    overall: float
    sleep: float
    activity: float
    nutrition: float
    mental: float
    hydration: float
    trend: str
    date: date


class WellnessAnalyticsService:
    """Service for calculating wellness scores and analyzing trends"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def calculate_wellness_score(
        self, 
        user_id: str, 
        target_date: Optional[date] = None
    ) -> WellnessScore:
        """Calculate overall wellness score for a user"""
        if target_date is None:
            target_date = date.today()
        
        # Calculate component scores
        sleep_score = await self._calculate_sleep_score(user_id, target_date)
        activity_score = await self._calculate_activity_score(user_id, target_date)
        nutrition_score = await self._calculate_nutrition_score(user_id, target_date)
        mental_score = await self._calculate_mental_score(user_id, target_date)
        hydration_score = await self._calculate_hydration_score(user_id, target_date)
        
        # Weighted average
        weights = {
            'sleep': 0.25,
            'activity': 0.25,
            'nutrition': 0.20,
            'mental': 0.20,
            'hydration': 0.10
        }
        
        overall = (
            sleep_score * weights['sleep'] +
            activity_score * weights['activity'] +
            nutrition_score * weights['nutrition'] +
            mental_score * weights['mental'] +
            hydration_score * weights['hydration']
        )
        
        # Determine trend
        trend = await self._calculate_trend(user_id, target_date)
        
        score = WellnessScore(
            overall=round(overall, 1),
            sleep=round(sleep_score, 1),
            activity=round(activity_score, 1),
            nutrition=round(nutrition_score, 1),
            mental=round(mental_score, 1),
            hydration=round(hydration_score, 1),
            trend=trend,
            date=target_date
        )
        
        # Save to database
        await self._save_wellness_score(user_id, score)
        
        return score
    
    async def _calculate_sleep_score(self, user_id: str, target_date: date) -> float:
        """Calculate sleep score (0-100)"""
        try:
            # Get sleep data for last 7 days
            start_date = target_date - timedelta(days=7)
            
            sleep_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'sleep_duration').gte(
                'recorded_at', start_date.isoformat()
            ).lte('recorded_at', target_date.isoformat()).execute()
            
            if not sleep_response.data:
                return 50.0  # Default score if no data
            
            # Calculate average sleep hours
            sleep_hours = [float(m['value']) for m in sleep_response.data]
            avg_sleep = sum(sleep_hours) / len(sleep_hours) if sleep_hours else 0
            
            # Score based on 7-9 hours optimal range
            if 7 <= avg_sleep <= 9:
                return 100.0
            elif 6 <= avg_sleep < 7 or 9 < avg_sleep <= 10:
                return 80.0
            elif 5 <= avg_sleep < 6 or 10 < avg_sleep <= 11:
                return 60.0
            elif 4 <= avg_sleep < 5:
                return 40.0
            else:
                return 20.0
                
        except Exception as e:
            logger.error(f"Error calculating sleep score: {e}")
            return 50.0
    
    async def _calculate_activity_score(self, user_id: str, target_date: date) -> float:
        """Calculate activity score (0-100)"""
        try:
            # Get steps data for last 7 days
            start_date = target_date - timedelta(days=7)
            
            steps_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'steps').gte(
                'recorded_at', start_date.isoformat()
            ).lte('recorded_at', target_date.isoformat()).execute()
            
            if not steps_response.data:
                return 50.0
            
            # Calculate average daily steps
            steps_by_date = {}
            for metric in steps_response.data:
                metric_date = datetime.fromisoformat(metric['recorded_at']).date()
                if metric_date not in steps_by_date:
                    steps_by_date[metric_date] = 0
                steps_by_date[metric_date] += float(metric['value'])
            
            if not steps_by_date:
                return 50.0
            
            avg_steps = sum(steps_by_date.values()) / len(steps_by_date)
            
            # Score based on 10,000 steps target
            if avg_steps >= 10000:
                return 100.0
            elif avg_steps >= 7500:
                return 80.0
            elif avg_steps >= 5000:
                return 60.0
            elif avg_steps >= 3000:
                return 40.0
            else:
                return 20.0
                
        except Exception as e:
            logger.error(f"Error calculating activity score: {e}")
            return 50.0
    
    async def _calculate_nutrition_score(self, user_id: str, target_date: date) -> float:
        """Calculate nutrition score (0-100)"""
        try:
            # Get nutrition data for last 7 days
            start_date = target_date - timedelta(days=7)
            
            # Check for any nutrition logging
            logs_response = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'nutrition').gte(
                'logged_at', start_date.isoformat()
            ).lte('logged_at', target_date.isoformat()).execute()
            
            # If user logs nutrition, give them credit
            if logs_response.data and len(logs_response.data) >= 3:
                return 75.0  # Good engagement
            
            # Check for calories data
            calories_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'nutrition_calories').gte(
                'recorded_at', start_date.isoformat()
            ).execute()
            
            if calories_response.data:
                return 70.0  # Has some nutrition data
            
            return 50.0  # Default if no data
            
        except Exception as e:
            logger.error(f"Error calculating nutrition score: {e}")
            return 50.0
    
    async def _calculate_mental_score(self, user_id: str, target_date: date) -> float:
        """Calculate mental wellbeing score (0-100)"""
        try:
            # Get mood and stress data for last 7 days
            start_date = target_date - timedelta(days=7)
            
            mood_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'mood').gte(
                'logged_at', start_date.isoformat()
            ).lte('logged_at', target_date.isoformat()).execute()
            
            stress_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'stress').gte(
                'logged_at', start_date.isoformat()
            ).lte('logged_at', target_date.isoformat()).execute()
            
            if not mood_logs.data and not stress_logs.data:
                return 50.0  # No data
            
            # Calculate average mood (assuming 1-10 scale)
            mood_scores = []
            if mood_logs.data:
                mood_scores = [float(m.get('value', 5)) for m in mood_logs.data if m.get('value')]
            
            # Calculate average stress (assuming 1-10 scale, inverted)
            stress_scores = []
            if stress_logs.data:
                stress_scores = [float(s.get('value', 5)) for s in stress_logs.data if s.get('value')]
            
            if not mood_scores and not stress_scores:
                return 50.0
            
            # Combine mood and stress (stress is inverted - lower is better)
            combined_scores = []
            if mood_scores:
                combined_scores.extend(mood_scores)
            if stress_scores:
                # Invert stress (10 - stress_value) to make higher better
                combined_scores.extend([10 - s for s in stress_scores])
            
            avg_score = sum(combined_scores) / len(combined_scores) if combined_scores else 5
            
            # Convert to 0-100 scale
            return (avg_score / 10) * 100
            
        except Exception as e:
            logger.error(f"Error calculating mental score: {e}")
            return 50.0
    
    async def _calculate_hydration_score(self, user_id: str, target_date: date) -> float:
        """Calculate hydration score (0-100)"""
        try:
            # Get water intake data for last 7 days
            start_date = target_date - timedelta(days=7)
            
            water_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'water').gte(
                'logged_at', start_date.isoformat()
            ).lte('logged_at', target_date.isoformat()).execute()
            
            # Also check health_metrics
            water_metrics = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'water_intake').gte(
                'recorded_at', start_date.isoformat()
            ).lte('recorded_at', target_date.isoformat()).execute()
            
            if not water_logs.data and not water_metrics.data:
                return 50.0  # No data
            
            # Calculate total water intake (assuming ml or oz)
            total_water = 0
            if water_logs.data:
                total_water += sum(float(m.get('value', 0)) for m in water_logs.data)
            if water_metrics.data:
                total_water += sum(float(m.get('value', 0)) for m in water_metrics.data)
            
            # Average daily (assuming 8 cups = 2000ml target)
            days_with_data = max(len(set(m.get('logged_at', '')[:10] for m in water_logs.data)), 1)
            avg_daily = total_water / days_with_data if days_with_data > 0 else 0
            
            # Score based on 2000ml (8 cups) target
            if avg_daily >= 2000:
                return 100.0
            elif avg_daily >= 1500:
                return 80.0
            elif avg_daily >= 1000:
                return 60.0
            elif avg_daily >= 500:
                return 40.0
            else:
                return 20.0
                
        except Exception as e:
            logger.error(f"Error calculating hydration score: {e}")
            return 50.0
    
    async def _calculate_trend(self, user_id: str, target_date: date) -> str:
        """Calculate trend (improving, stable, declining)"""
        try:
            # Get scores for last 3 days
            scores = []
            for i in range(3):
                check_date = target_date - timedelta(days=i)
                score_response = self.supabase.table('wellness_scores').select('overall_score').eq(
                    'user_id', user_id
                ).eq('score_date', check_date.isoformat()).execute()
                
                if score_response.data:
                    scores.append(score_response.data[0]['overall_score'])
            
            if len(scores) < 2:
                return 'stable'
            
            # Compare recent scores
            if len(scores) >= 2:
                recent = scores[0]
                previous = scores[1]
                
                if recent > previous + 2:
                    return 'improving'
                elif recent < previous - 2:
                    return 'declining'
            
            return 'stable'
            
        except Exception as e:
            logger.error(f"Error calculating trend: {e}")
            return 'stable'
    
    async def _save_wellness_score(self, user_id: str, score: WellnessScore):
        """Save wellness score to database"""
        try:
            self.supabase.table('wellness_scores').upsert({
                'user_id': user_id,
                'score_date': score.date.isoformat(),
                'overall_score': score.overall,
                'sleep_score': score.sleep,
                'activity_score': score.activity,
                'nutrition_score': score.nutrition,
                'mental_wellbeing_score': score.mental,
                'hydration_score': score.hydration,
                'trend': score.trend,
                'score_components': {
                    'weights': {
                        'sleep': 0.25,
                        'activity': 0.25,
                        'nutrition': 0.20,
                        'mental': 0.20,
                        'hydration': 0.10
                    }
                }
            }, on_conflict='user_id,score_date').execute()
            
        except Exception as e:
            logger.error(f"Error saving wellness score: {e}")


# Global instance
wellness_analytics_service = WellnessAnalyticsService()
