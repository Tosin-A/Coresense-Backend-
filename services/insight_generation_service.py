"""
Insight Generation Service
Generates personalized, actionable insights from health data
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from backend.database.supabase_client import get_supabase_client
from backend.services.wellness_analytics_service import wellness_analytics_service

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    title: str
    body: str
    category: str
    trend: str
    trend_value: Optional[str]
    actionable: bool
    action_text: Optional[str]
    priority: int
    wellness_score: Optional[float] = None
    related_goal_id: Optional[str] = None


class InsightGenerationService:
    """Service for generating personalized insights"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def generate_insights(
        self, 
        user_id: str, 
        period: str = "weekly"
    ) -> List[Dict]:
        """Generate insights for a user"""
        try:
            insights = []
            
            # Get wellness score
            wellness_score = await wellness_analytics_service.calculate_wellness_score(user_id)
            
            # Generate insights for each category
            sleep_insights = await self._generate_sleep_insights(user_id, wellness_score)
            activity_insights = await self._generate_activity_insights(user_id, wellness_score)
            nutrition_insights = await self._generate_nutrition_insights(user_id, wellness_score)
            mental_insights = await self._generate_mental_insights(user_id, wellness_score)
            hydration_insights = await self._generate_hydration_insights(user_id, wellness_score)
            
            # Combine all insights
            all_insights = (
                sleep_insights + activity_insights + 
                nutrition_insights + mental_insights + hydration_insights
            )
            
            # Sort by priority
            all_insights.sort(key=lambda x: x.priority, reverse=True)
            
            # Convert to dict format
            insights_dict = []
            for insight in all_insights[:10]:  # Top 10 insights
                insights_dict.append({
                    'title': insight.title,
                    'body': insight.body,
                    'category': insight.category,
                    'trend': insight.trend,
                    'trend_value': insight.trend_value,
                    'actionable': insight.actionable,
                    'action_text': insight.action_text,
                    'priority': insight.priority,
                    'wellness_score': insight.wellness_score,
                    'related_goal_id': insight.related_goal_id
                })
            
            return insights_dict
            
        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            return []
    
    async def _generate_sleep_insights(
        self, 
        user_id: str, 
        wellness_score
    ) -> List[Insight]:
        """Generate sleep-related insights"""
        insights = []
        
        try:
            # Get sleep data for last 7 days
            start_date = date.today() - timedelta(days=7)
            
            sleep_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'sleep_duration').gte(
                'recorded_at', start_date.isoformat()
            ).execute()
            
            if not sleep_response.data:
                return insights
            
            sleep_hours = [float(m['value']) for m in sleep_response.data]
            avg_sleep = sum(sleep_hours) / len(sleep_hours) if sleep_hours else 0
            
            # Compare with previous week
            prev_start = start_date - timedelta(days=7)
            prev_sleep_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'sleep_duration').gte(
                'recorded_at', prev_start.isoformat()
            ).lt('recorded_at', start_date.isoformat()).execute()
            
            prev_avg = 0
            if prev_sleep_response.data:
                prev_hours = [float(m['value']) for m in prev_sleep_response.data]
                prev_avg = sum(prev_hours) / len(prev_hours) if prev_hours else 0
            
            # Generate insight based on sleep patterns
            if avg_sleep < 7:
                trend_value = f"{avg_sleep:.1f}h"
                if prev_avg > 0 and avg_sleep < prev_avg:
                    trend = "down"
                    trend_value = f"-{prev_avg - avg_sleep:.1f}h"
                else:
                    trend = "stable"
                
                insights.append(Insight(
                    title="Sleep Improvement Opportunity",
                    body=f"You slept {avg_sleep:.1f} hours on average this week; try to aim for 7-8 hours to improve recovery.",
                    category="sleep",
                    trend=trend,
                    trend_value=trend_value,
                    actionable=True,
                    action_text="Set bedtime reminder for 10 PM",
                    priority=85,
                    wellness_score=wellness_score.sleep
                ))
            elif avg_sleep > 9:
                insights.append(Insight(
                    title="Sleep Duration Notice",
                    body=f"You're averaging {avg_sleep:.1f} hours of sleep. While rest is important, excessive sleep may indicate other health factors.",
                    category="sleep",
                    trend="stable",
                    trend_value=f"{avg_sleep:.1f}h",
                    actionable=False,
                    action_text=None,
                    priority=60,
                    wellness_score=wellness_score.sleep
                ))
            elif wellness_score.sleep >= 90:
                insights.append(Insight(
                    title="Great Sleep Habits!",
                    body=f"You're maintaining excellent sleep patterns with an average of {avg_sleep:.1f} hours. Keep it up!",
                    category="sleep",
                    trend="stable",
                    trend_value=None,
                    actionable=False,
                    action_text=None,
                    priority=40,
                    wellness_score=wellness_score.sleep
                ))
            
            # Check for consistency
            if len(sleep_hours) >= 5:
                sleep_std = self._calculate_std(sleep_hours)
                if sleep_std > 2:
                    insights.append(Insight(
                        title="Sleep Schedule Consistency",
                        body="Your sleep schedule varies significantly. Consistency improves sleep quality and recovery.",
                        category="sleep",
                        trend="stable",
                        trend_value=f"±{sleep_std:.1f}h variance",
                        actionable=True,
                        action_text="Set consistent bedtime and wake time",
                        priority=70,
                        wellness_score=wellness_score.sleep
                    ))
            
        except Exception as e:
            logger.error(f"Error generating sleep insights: {e}")
        
        return insights
    
    async def _generate_activity_insights(
        self, 
        user_id: str, 
        wellness_score
    ) -> List[Insight]:
        """Generate activity-related insights"""
        insights = []
        
        try:
            start_date = date.today() - timedelta(days=7)
            
            steps_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'steps').gte(
                'recorded_at', start_date.isoformat()
            ).execute()
            
            if not steps_response.data:
                return insights
            
            # Calculate average daily steps
            steps_by_date = {}
            for metric in steps_response.data:
                metric_date = datetime.fromisoformat(metric['recorded_at']).date()
                if metric_date not in steps_by_date:
                    steps_by_date[metric_date] = 0
                steps_by_date[metric_date] += float(metric['value'])
            
            if not steps_by_date:
                return insights
            
            avg_steps = sum(steps_by_date.values()) / len(steps_by_date)
            
            # Compare with previous week
            prev_start = start_date - timedelta(days=7)
            prev_steps_response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'steps').gte(
                'recorded_at', prev_start.isoformat()
            ).lt('recorded_at', start_date.isoformat()).execute()
            
            prev_avg = 0
            if prev_steps_response.data:
                prev_steps_by_date = {}
                for metric in prev_steps_response.data:
                    metric_date = datetime.fromisoformat(metric['recorded_at']).date()
                    if metric_date not in prev_steps_by_date:
                        prev_steps_by_date[metric_date] = 0
                    prev_steps_by_date[metric_date] += float(metric['value'])
                
                if prev_steps_by_date:
                    prev_avg = sum(prev_steps_by_date.values()) / len(prev_steps_by_date)
            
            # Generate insights
            if avg_steps < 10000:
                trend = "stable"
                trend_value = f"{int(avg_steps):,} steps/day"
                
                if prev_avg > 0:
                    change_pct = ((avg_steps - prev_avg) / prev_avg) * 100
                    if change_pct < -10:
                        trend = "down"
                        trend_value = f"-{abs(int(change_pct))}%"
                    elif change_pct > 10:
                        trend = "up"
                        trend_value = f"+{int(change_pct)}%"
                
                insights.append(Insight(
                    title="Activity Goal Opportunity",
                    body=f"You averaged {int(avg_steps):,} steps this week. Aim for 10,000 steps daily for optimal health.",
                    category="activity",
                    trend=trend,
                    trend_value=trend_value,
                    actionable=True,
                    action_text=f"Add a {int((10000 - avg_steps) / 2000)} minute walk to your routine",
                    priority=80,
                    wellness_score=wellness_score.activity
                ))
            elif avg_steps >= 10000:
                insights.append(Insight(
                    title="Excellent Activity Level!",
                    body=f"You're exceeding the 10,000 steps goal with an average of {int(avg_steps):,} steps. Great work!",
                    category="activity",
                    trend="up",
                    trend_value=f"{int(avg_steps):,} steps/day",
                    actionable=False,
                    action_text=None,
                    priority=30,
                    wellness_score=wellness_score.activity
                ))
            
        except Exception as e:
            logger.error(f"Error generating activity insights: {e}")
        
        return insights
    
    async def _generate_nutrition_insights(
        self, 
        user_id: str, 
        wellness_score
    ) -> List[Insight]:
        """Generate nutrition-related insights"""
        insights = []
        
        try:
            start_date = date.today() - timedelta(days=7)
            
            nutrition_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'nutrition').gte(
                'logged_at', start_date.isoformat()
            ).execute()
            
            if not nutrition_logs.data:
                insights.append(Insight(
                    title="Start Tracking Nutrition",
                    body="Tracking your nutrition helps identify patterns and improve your wellness score.",
                    category="nutrition",
                    trend="stable",
                    trend_value=None,
                    actionable=True,
                    action_text="Log your meals this week",
                    priority=65,
                    wellness_score=wellness_score.nutrition
                ))
            elif len(nutrition_logs.data) < 3:
                insights.append(Insight(
                    title="Increase Nutrition Tracking",
                    body=f"You've logged nutrition {len(nutrition_logs.data)} times this week. More frequent tracking provides better insights.",
                    category="nutrition",
                    trend="stable",
                    trend_value=f"{len(nutrition_logs.data)} logs",
                    actionable=True,
                    action_text="Log at least one meal per day",
                    priority=60,
                    wellness_score=wellness_score.nutrition
                ))
            
        except Exception as e:
            logger.error(f"Error generating nutrition insights: {e}")
        
        return insights
    
    async def _generate_mental_insights(
        self, 
        user_id: str, 
        wellness_score
    ) -> List[Insight]:
        """Generate mental wellbeing insights"""
        insights = []
        
        try:
            start_date = date.today() - timedelta(days=7)
            
            mood_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'mood').gte(
                'logged_at', start_date.isoformat()
            ).execute()
            
            stress_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'stress').gte(
                'logged_at', start_date.isoformat()
            ).execute()
            
            if not mood_logs.data and not stress_logs.data:
                insights.append(Insight(
                    title="Track Your Mood",
                    body="Logging your mood and stress levels helps identify patterns and improve mental wellbeing.",
                    category="mental",
                    trend="stable",
                    trend_value=None,
                    actionable=True,
                    action_text="Log your mood daily",
                    priority=70,
                    wellness_score=wellness_score.mental
                ))
                return insights
            
            # Analyze mood
            if mood_logs.data:
                mood_values = [float(m.get('value', 5)) for m in mood_logs.data if m.get('value')]
                if mood_values:
                    avg_mood = sum(mood_values) / len(mood_values)
                    
                    if avg_mood < 5:
                        insights.append(Insight(
                            title="Mood Support",
                            body=f"Your mood averaged {avg_mood:.1f}/10 this week. Consider activities that bring you joy or speak with someone you trust.",
                            category="mental",
                            trend="down",
                            trend_value=f"{avg_mood:.1f}/10",
                            actionable=True,
                            action_text="Try 5-minute breathing exercises daily",
                            priority=85,
                            wellness_score=wellness_score.mental
                        ))
            
            # Analyze stress
            if stress_logs.data:
                stress_values = [float(s.get('value', 5)) for s in stress_logs.data if s.get('value')]
                if stress_values:
                    avg_stress = sum(stress_values) / len(stress_values)
                    
                    if avg_stress > 7:
                        insights.append(Insight(
                            title="High Stress Levels",
                            body=f"Your stress levels averaged {avg_stress:.1f}/10 this week. Try stress-reduction techniques like meditation or exercise.",
                            category="mental",
                            trend="up",
                            trend_value=f"{avg_stress:.1f}/10",
                            actionable=True,
                            action_text="Try 5-minute meditation daily",
                            priority=90,
                            wellness_score=wellness_score.mental
                        ))
            
        except Exception as e:
            logger.error(f"Error generating mental insights: {e}")
        
        return insights
    
    async def _generate_hydration_insights(
        self, 
        user_id: str, 
        wellness_score
    ) -> List[Insight]:
        """Generate hydration insights"""
        insights = []
        
        try:
            start_date = date.today() - timedelta(days=7)
            
            water_logs = self.supabase.table('manual_health_logs').select('*').eq(
                'user_id', user_id
            ).eq('log_type', 'water').gte(
                'logged_at', start_date.isoformat()
            ).execute()
            
            water_metrics = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', 'water_intake').gte(
                'recorded_at', start_date.isoformat()
            ).execute()
            
            if not water_logs.data and not water_metrics.data:
                insights.append(Insight(
                    title="Track Water Intake",
                    body="Staying hydrated is essential for health. Aim for 8 cups (2L) of water daily.",
                    category="hydration",
                    trend="stable",
                    trend_value=None,
                    actionable=True,
                    action_text="Log your water intake",
                    priority=65,
                    wellness_score=wellness_score.hydration
                ))
                return insights
            
            # Calculate average daily water
            total_water = 0
            if water_logs.data:
                total_water += sum(float(m.get('value', 0)) for m in water_logs.data)
            if water_metrics.data:
                total_water += sum(float(m.get('value', 0)) for m in water_metrics.data)
            
            days_with_data = max(len(set(m.get('logged_at', '')[:10] for m in water_logs.data)), 1)
            avg_daily = total_water / days_with_data if days_with_data > 0 else 0
            
            if avg_daily < 1500:  # Less than ~6 cups
                insights.append(Insight(
                    title="Increase Hydration",
                    body=f"You're averaging {int(avg_daily)}ml of water daily. Aim for 2000ml (8 cups) for optimal hydration.",
                    category="hydration",
                    trend="stable",
                    trend_value=f"{int(avg_daily)}ml/day",
                    actionable=True,
                    action_text=f"Drink {int((2000 - avg_daily) / 250)} more glasses today",
                    priority=75,
                    wellness_score=wellness_score.hydration
                ))
            
        except Exception as e:
            logger.error(f"Error generating hydration insights: {e}")
        
        return insights
    
    def _calculate_std(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


# Global instance
insight_generation_service = InsightGenerationService()
