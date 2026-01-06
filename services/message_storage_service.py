"""
Message Storage Service - Persists messages to the messages table in Supabase
"""

import logging
from datetime import datetime
from typing import Optional
import uuid

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class MessageStorageService:
    """
    Service for storing chat messages in the messages table
    
    Handles persistence of both user messages and assistant responses
    to support chat history and app display.
    """
    
    def __init__(self):
        pass
    
    async def store_user_message(
        self,
        user_id: str,
        content: str,
        thread_id: str
    ) -> str:
        """
        Store user message in database.
        
        Args:
            user_id: The user's UUID
            content: The message text
            thread_id: The OpenAI thread ID
            
        Returns:
            The chat_id (UUID) for linking to assistant response
        """
        try:
            supabase = get_supabase_client()
            chat_id = str(uuid.uuid4())
            
            supabase.table("messages").insert({
                "chat_id": chat_id,
                "userid": user_id,
                "direction": "incoming",
                "sender_type": "user",
                "content": content,
                "message_type": "text",
                "read_in_app": False,
                "created_at": datetime.now().isoformat(),
                "metadata": {"thread_id": thread_id}
            }).execute()
            
            logger.info(f"💾 Stored user message: chat_id={chat_id}, user_id={user_id}")
            return chat_id
            
        except Exception as e:
            logger.error(f"❌ Error storing user message: {e}")
            # Return None so the chat can continue even if storage fails
            return None
    
    async def store_assistant_message(
        self,
        user_id: str,
        content: str,
        thread_id: str,
        chat_id: str
    ) -> Optional[str]:
        """
        Store assistant message in database, linked to user message.
        
        Args:
            user_id: The user's UUID
            content: The assistant's response text
            thread_id: The OpenAI thread ID
            chat_id: The chat_id from the user message to link to
            
        Returns:
            The message id if successful, None otherwise
        """
        try:
            if not chat_id:
                logger.warning("No chat_id provided for assistant message, skipping storage")
                return None
            
            supabase = get_supabase_client()
            message_id = str(uuid.uuid4())
            
            supabase.table("messages").insert({
                "id": message_id,
                "chat_id": chat_id,
                "userid": user_id,
                "direction": "outgoing",
                "sender_type": "gpt",
                "content": content,
                "message_type": "text",
                "read_in_app": False,
                "delivered": True,
                "created_at": datetime.now().isoformat(),
                "metadata": {"thread_id": thread_id}
            }).execute()
            
            logger.info(f"💾 Stored assistant message: message_id={message_id}, chat_id={chat_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"❌ Error storing assistant message: {e}")
            return None
    
    async def store_message_pair(
        self,
        user_id: str,
        user_content: str,
        assistant_content: str,
        thread_id: str
    ) -> tuple[str, str]:
        """
        Store both user and assistant messages in a single operation.
        
        Args:
            user_id: The user's UUID
            user_content: The user's message text
            assistant_content: The assistant's response text
            thread_id: The OpenAI thread ID
            
        Returns:
            Tuple of (chat_id, message_id)
        """
        chat_id = await self.store_user_message(user_id, user_content, thread_id)
        message_id = await self.store_assistant_message(user_id, assistant_content, thread_id, chat_id)
        return chat_id, message_id


# Global message storage service instance
message_storage = MessageStorageService()
