"""
Waiting Messages Notification Service
Handles push notifications for coach messages when app is closed
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

@dataclass
class WaitingMessage:
    user_id: str
    message_text: str
    message_type: str = "coach_message"
    priority: str = "normal"  # low, normal, high, urgent
    scheduled_for: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None

class NotificationService:
    """Service for managing waiting messages and notifications"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
        self.message_queue: List[WaitingMessage] = []
    
    async def queue_waiting_message(self, message: WaitingMessage) -> bool:
        """Queue a message to be sent when user becomes available"""
        try:
            # Store in database for persistence
            await self._store_waiting_message(message)
            
            # Add to in-memory queue for immediate processing
            self.message_queue.append(message)
            
            # Attempt immediate delivery if user is active
            if await self._is_user_active(message.user_id):
                await self._deliver_message_immediately(message)
            else:
                logger.info(f"Queued waiting message for user {message.user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error queueing waiting message: {e}")
            return False
    
    async def get_waiting_messages(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all waiting messages for a user"""
        try:
            response = self.supabase.table('waiting_messages').select('*').eq(
                'user_id', user_id
            ).eq('delivered', False).order('created_at', asc=True).execute()
            
            messages = []
            if response.data:
                for msg in response.data:
                    messages.append({
                        "id": msg['id'],
                        "message_text": msg['message_text'],
                        "message_type": msg.get('message_type', 'coach_message'),
                        "priority": msg.get('priority', 'normal'),
                        "created_at": msg['created_at'],
                        "context": msg.get('context', {})
                    })
            
            return messages
            
        except Exception as e:
            logger.error(f"Error getting waiting messages for {user_id}: {e}")
            return []
    
    async def mark_message_delivered(self, message_id: str) -> bool:
        """Mark a waiting message as delivered"""
        try:
            self.supabase.table('waiting_messages').update({
                'delivered': True,
                'delivered_at': datetime.now().isoformat()
            }).eq('id', message_id).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error marking message delivered: {e}")
            return False
    
    async def process_delayed_messages(self) -> int:
        """Process messages that are scheduled for future delivery"""
        try:
            now = datetime.now()
            
            # Get messages scheduled for now or past
            response = self.supabase.table('waiting_messages').select('*').eq(
                'delivered', False
            ).lte('scheduled_for', now.isoformat()).execute()
            
            processed_count = 0
            if response.data:
                for msg in response.data:
                    # Check if user is now active
                    if await self._is_user_active(msg['user_id']):
                        await self._deliver_message_immediately(WaitingMessage(
                            user_id=msg['user_id'],
                            message_text=msg['message_text'],
                            message_type=msg.get('message_type', 'coach_message'),
                            priority=msg.get('priority', 'normal'),
                            context=msg.get('context', {})
                        ))
                        
                        # Mark as delivered
                        await self.mark_message_delivered(msg['id'])
                        processed_count += 1
            
            return processed_count
            
        except Exception as e:
            logger.error(f"Error processing delayed messages: {e}")
            return 0
    
    async def send_coach_checkin(self, user_id: str, message: str, priority: str = "normal") -> bool:
        """Send a coach check-in message"""
        waiting_message = WaitingMessage(
            user_id=user_id,
            message_text=message,
            message_type="coach_checkin",
            priority=priority
        )
        
        return await self.queue_waiting_message(waiting_message)
    
    async def send_pattern_alert(self, user_id: str, pattern_type: str, message: str) -> bool:
        """Send a pattern-based alert message"""
        waiting_message = WaitingMessage(
            user_id=user_id,
            message_text=message,
            message_type="pattern_alert",
            priority="high"
        )
        
        return await self.queue_waiting_message(waiting_message)
    
    async def send_accountability_nudge(self, user_id: str, nudge_type: str, message: str) -> bool:
        """Send an accountability nudge"""
        waiting_message = WaitingMessage(
            user_id=user_id,
            message_text=message,
            message_type="accountability_nudge",
            priority="urgent" if nudge_type == "deadline" else "normal"
        )
        
        return await self.queue_waiting_message(waiting_message)
    
    async def _store_waiting_message(self, message: WaitingMessage) -> bool:
        """Store waiting message in database"""
        try:
            self.supabase.table('waiting_messages').insert({
                'user_id': message.user_id,
                'message_text': message.message_text,
                'message_type': message.message_type,
                'priority': message.priority,
                'scheduled_for': message.scheduled_for.isoformat() if message.scheduled_for else None,
                'context': message.context or {},
                'delivered': False,
                'created_at': datetime.now().isoformat()
            }).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing waiting message: {e}")
            return False
    
    async def _is_user_active(self, user_id: str) -> bool:
        """Check if user is currently active (has recent app usage)"""
        try:
            # Check for recent coach messages (user replied recently)
            recent_cutoff = (datetime.now() - timedelta(hours=2)).isoformat()
            
            response = self.supabase.table('messages').select('id').eq(
                'user_id', user_id
            ).gte('created_at', recent_cutoff).execute()
            
            return len(response.data) > 0 if response.data else False
            
        except Exception as e:
            logger.error(f"Error checking user activity: {e}")
            return False
    
    async def _deliver_message_immediately(self, message: WaitingMessage) -> bool:
        """Deliver message immediately (this would integrate with push notifications)"""
        try:
            # For now, just log the delivery
            logger.info(f"Delivering immediate message to {message.user_id}: {message.message_text}")
            
            # In a real implementation, this would:
            # 1. Send push notification via Firebase/APNs
            # 2. Update app badge count
            # 3. Show notification on lock screen
            # 4. Trigger notification sound/vibration
            
            # For demo purposes, we'll just store it as delivered
            return True
            
        except Exception as e:
            logger.error(f"Error delivering message immediately: {e}")
            return False
    
    async def get_notification_stats(self, user_id: str) -> Dict[str, Any]:
        """Get notification statistics for a user"""
        try:
            # Get message counts by type
            total_response = self.supabase.table('waiting_messages').select('id', count='exact').eq(
                'user_id', user_id
            ).execute()
            
            delivered_response = self.supabase.table('waiting_messages').select('id', count='exact').eq(
                'user_id', user_id
            ).eq('delivered', True).execute()
            
            pending_response = self.supabase.table('waiting_messages').select('id', count='exact').eq(
                'user_id', user_id
            ).eq('delivered', False).execute()
            
            return {
                "total_messages": total_response.count or 0,
                "delivered_messages": delivered_response.count or 0,
                "pending_messages": pending_response.count or 0,
                "last_message_at": await self._get_last_message_time(user_id)
            }
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {
                "total_messages": 0,
                "delivered_messages": 0,
                "pending_messages": 0,
                "last_message_at": None
            }
    
    async def _get_last_message_time(self, user_id: str) -> Optional[str]:
        """Get timestamp of last message for user"""
        try:
            response = self.supabase.table('waiting_messages').select('created_at').eq(
                'user_id', user_id
            ).order('created_at', desc=True).limit(1).execute()
            
            return response.data[0]['created_at'] if response.data else None
            
        except Exception as e:
            logger.error(f"Error getting last message time: {e}")
            return None

# Global notification service instance
notification_service = NotificationService()

# Background task to process delayed messages
async def process_pending_notifications():
    """Background task to process pending notifications"""
    while True:
        try:
            processed = await notification_service.process_delayed_messages()
            if processed > 0:
                logger.info(f"Processed {processed} delayed messages")
            
            # Wait 30 seconds before next check
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in notification processing task: {e}")
            await asyncio.sleep(60)  # Wait longer on error