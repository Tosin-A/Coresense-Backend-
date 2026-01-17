"""
Goal Management Service
Manages wellness goals and tracks progress
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class GoalManagementService:
    """Service for managing wellness goals"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def create_goal(self, user_id: str, goal_data: Dict) -> Dict:
        """Create a new wellness goal"""
        try:
            goal = {
                'user_id': user_id,
                'goal_type': goal_data['goal_type'],
                'target_value': goal_data['target_value'],
                'unit': goal_data.get('unit', self._get_default_unit(goal_data['goal_type'])),
                'period': goal_data.get('period', 'daily'),
                'start_date': goal_data.get('start_date', date.today().isoformat()),
                'status': 'active',
                'current_value': 0
            }
            
            if 'end_date' in goal_data:
                goal['end_date'] = goal_data['end_date']
            
            response = self.supabase.table('wellness_goals').insert(goal).execute()
            
            if response.data:
                return self._format_goal(response.data[0])
            
            return {}
            
        except Exception as e:
            logger.error(f"Error creating goal: {e}")
            raise
    
    async def get_goals(self, user_id: str, status: Optional[str] = 'active') -> List[Dict]:
        """Get user's goals"""
        try:
            query = self.supabase.table('wellness_goals').select('*').eq('user_id', user_id)
            
            if status:
                query = query.eq('status', status)
            
            response = query.order('created_at', desc=True).execute()
            
            goals = []
            if response.data:
                for goal in response.data:
                    formatted = self._format_goal(goal)
                    # Update current value based on recent data
                    formatted['current_value'] = await self._calculate_current_value(
                        user_id, 
                        goal['goal_type'],
                        goal['period']
                    )
                    formatted['progress_percentage'] = self._calculate_progress(
                        formatted['current_value'],
                        formatted['target_value']
                    )
                    goals.append(formatted)
            
            return goals
            
        except Exception as e:
            logger.error(f"Error getting goals: {e}")
            return []
    
    async def update_goal(self, goal_id: str, user_id: str, updates: Dict) -> Dict:
        """Update a goal"""
        try:
            update_data = {**updates, 'updated_at': datetime.now().isoformat()}
            
            response = self.supabase.table('wellness_goals').update(update_data).eq(
                'id', goal_id
            ).eq('user_id', user_id).execute()
            
            if response.data:
                return self._format_goal(response.data[0])
            
            return {}
            
        except Exception as e:
            logger.error(f"Error updating goal: {e}")
            raise
    
    async def delete_goal(self, goal_id: str, user_id: str) -> bool:
        """Delete a goal"""
        try:
            self.supabase.table('wellness_goals').delete().eq(
                'id', goal_id
            ).eq('user_id', user_id).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting goal: {e}")
            return False
    
    async def get_goal_suggestions(self, user_id: str) -> List[Dict]:
        """Get suggested goals based on user's data"""
        try:
            suggestions = []
            
            # Get wellness score to identify areas for improvement
            from backend.services.wellness_analytics_service import wellness_analytics_service
            score = await wellness_analytics_service.calculate_wellness_score(user_id)
            
            # Suggest goals based on lower scores
            if score.sleep < 70:
                suggestions.append({
                    'goal_type': 'sleep',
                    'target_value': 7.5,
                    'unit': 'hours',
                    'period': 'daily',
                    'suggestion_reason': 'Your sleep score could improve'
                })
            
            if score.activity < 70:
                suggestions.append({
                    'goal_type': 'steps',
                    'target_value': 10000,
                    'unit': 'steps',
                    'period': 'daily',
                    'suggestion_reason': 'Increase your activity level'
                })
            
            if score.hydration < 70:
                suggestions.append({
                    'goal_type': 'water',
                    'target_value': 2000,
                    'unit': 'ml',
                    'period': 'daily',
                    'suggestion_reason': 'Improve hydration'
                })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting goal suggestions: {e}")
            return []
    
    async def _calculate_current_value(
        self, 
        user_id: str, 
        goal_type: str, 
        period: str
    ) -> float:
        """Calculate current value for a goal"""
        try:
            if period == 'daily':
                target_date = date.today()
            elif period == 'weekly':
                # Get current week's data
                target_date = date.today()
            else:
                target_date = date.today()
            
            # Map goal types to metric types
            metric_type_map = {
                'steps': 'steps',
                'sleep': 'sleep_duration',
                'water': 'water_intake',
                'activity': 'steps'
            }
            
            metric_type = metric_type_map.get(goal_type)
            if not metric_type:
                return 0.0
            
            # Get data for today or this week
            if period == 'daily':
                start_date = target_date
                end_date = target_date
            else:
                start_date = target_date
                end_date = target_date
            
            # Check health_metrics
            response = self.supabase.table('health_metrics').select('*').eq(
                'user_id', user_id
            ).eq('metric_type', metric_type).gte(
                'recorded_at', start_date.isoformat()
            ).lte('recorded_at', end_date.isoformat()).execute()
            
            if response.data:
                if period == 'daily':
                    return sum(float(m['value']) for m in response.data)
                else:
                    # Average for period
                    values = [float(m['value']) for m in response.data]
                    return sum(values) / len(values) if values else 0.0
            
            # Check manual logs
            log_type_map = {
                'water': 'water',
                'mood': 'mood',
                'stress': 'stress'
            }
            
            log_type = log_type_map.get(goal_type)
            if log_type:
                log_response = self.supabase.table('manual_health_logs').select('*').eq(
                    'user_id', user_id
                ).eq('log_type', log_type).gte(
                    'logged_at', start_date.isoformat()
                ).lte('logged_at', end_date.isoformat()).execute()
                
                if log_response.data:
                    if period == 'daily':
                        return sum(float(m.get('value', 0)) for m in log_response.data)
                    else:
                        values = [float(m.get('value', 0)) for m in log_response.data]
                        return sum(values) / len(values) if values else 0.0
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating current value: {e}")
            return 0.0
    
    def _calculate_progress(self, current: float, target: float) -> float:
        """Calculate progress percentage"""
        if target == 0:
            return 0.0
        progress = (current / target) * 100
        return min(progress, 100.0)
    
    def _format_goal(self, goal: Dict) -> Dict:
        """Format goal for API response"""
        return {
            'id': goal['id'],
            'goal_type': goal['goal_type'],
            'target_value': float(goal['target_value']),
            'current_value': float(goal.get('current_value', 0)),
            'unit': goal['unit'],
            'period': goal['period'],
            'start_date': goal['start_date'],
            'end_date': goal.get('end_date'),
            'status': goal['status'],
            'created_at': goal['created_at']
        }
    
    def _get_default_unit(self, goal_type: str) -> str:
        """Get default unit for goal type"""
        units = {
            'steps': 'steps',
            'sleep': 'hours',
            'water': 'ml',
            'mood': 'rating',
            'stress': 'rating',
            'nutrition': 'calories',
            'activity': 'minutes'
        }
        return units.get(goal_type, 'units')


# Global instance
goal_management_service = GoalManagementService()
