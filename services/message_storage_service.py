"""
Message Storage Service - Persists messages to the messages table in Supabase
"""

import logging
from datetime import datetime
from typing import Optional
import uuid

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class MessageStorageService:
    """
    Service for storing chat messages in the messages table
    
    Handles persistence of both user messages and assistant responses
    to support chat history and app display.
    """
    
    async def store_user_message(
        self,
        user_id: str,
        content: str,
        conversation_id: str = None,
        client_temp_id: Optional[str] = None,
        # Deprecated alias
        thread_id: str = None,
    ) -> str:
        """
        Store user message in database.

        Returns:
            The chat_id (UUID) for linking to assistant response
        """
        try:
            supabase = get_supabase_client()
            chat_id = str(uuid.uuid4())

            cid = conversation_id or thread_id
            insert_data = {
                "chat_id": chat_id,
                "userid": user_id,
                "direction": "incoming",
                "sender_type": "user",
                "content": content,
                "message_type": "text",
                "read_in_app": False,
                "created_at": datetime.now().isoformat(),
                "metadata": {"conversation_id": cid}
            }

            if client_temp_id:
                insert_data["client_temp_id"] = client_temp_id

            supabase.table("messages").insert(insert_data).execute()

            logger.info("Stored user message")
            return chat_id

        except Exception as e:
            logger.error(f"Error storing user message to Supabase: {e}")
            return None
    
    async def store_assistant_message(
        self,
        user_id: str,
        content: str,
        conversation_id: str = None,
        chat_id: str = None,
        response_id: Optional[str] = None,
        assistant_temp_id: Optional[str] = None,
        # Deprecated aliases
        thread_id: str = None,
        run_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Store assistant message in database, linked to user message.

        Returns:
            The message id if successful, None otherwise
        """
        try:
            if not chat_id:
                logger.warning("No chat_id provided for assistant message, skipping storage")
                return None

            supabase = get_supabase_client()
            message_id = str(uuid.uuid4())

            cid = conversation_id or thread_id
            rid = response_id or run_id

            insert_data = {
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
                "metadata": {"conversation_id": cid}
            }

            if rid:
                insert_data["run_id"] = rid

            if assistant_temp_id:
                insert_data["assistant_temp_id"] = assistant_temp_id

            supabase.table("messages").insert(insert_data).execute()

            logger.info(f"Stored assistant message: message_id={message_id}, chat_id={chat_id}, response_id={rid}")
            return message_id

        except Exception as e:
            logger.error(f"Error storing assistant message to Supabase: {e}")
            return None
    
    async def store_message_pair(
        self,
        user_id: str,
        user_content: str,
        assistant_content: str,
        conversation_id: str = None,
        thread_id: str = None,
    ) -> tuple[str, str]:
        """Store both user and assistant messages in a single operation."""
        cid = conversation_id or thread_id
        chat_id = await self.store_user_message(user_id, user_content, conversation_id=cid)
        message_id = await self.store_assistant_message(user_id, assistant_content, conversation_id=cid, chat_id=chat_id)
        return chat_id, message_id


# Global message storage service instance
message_storage = MessageStorageService()
