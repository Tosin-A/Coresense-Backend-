"""
Supabase database client singleton.
Provides typed access to Supabase tables.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from supabase import create_client, Client
import logging

from backend.config import get_settings
from backend.utils.supabase_utils import (
    extract_supabase_data,
    get_first_item_or_none,
    handle_supabase_error
)
from backend.utils.exceptions import DatabaseError, NotFoundError

logger = logging.getLogger(__name__)


# Global Supabase client instance
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get singleton Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
    return _supabase_client


# Helper functions for querying tables

def get_user_phone_numbers(user_id: str) -> List[Dict[str, Any]]:
    """Get all phone numbers registered for a user."""
    try:
        client = get_supabase_client()
        response = client.table("user_phone_numbers")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        return extract_supabase_data(response, default=[])
    except Exception as e:
        handle_supabase_error(e, "Failed to retrieve user phone numbers")
        return []


def create_user_phone_number(user_id: str, phone_number: str, is_verified: bool = False) -> Dict[str, Any]:
    """Register a phone number for a user."""
    try:
        client = get_supabase_client()
        response = client.table("user_phone_numbers")\
            .insert({
                "user_id": user_id,
                "phone_number": phone_number,
                "is_verified": is_verified
            })\
            .execute()
        result = get_first_item_or_none(response, "Failed to create user phone number")
        if result:
            return result
        raise DatabaseError("Failed to create user phone number: No data returned")
    except DatabaseError:
        raise
    except Exception as e:
        handle_supabase_error(e, "Failed to create user phone number")


def get_user_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Get user by phone number.
    Returns user data including user_id.
    Handles phone number format variations.
    """
    try:
        client = get_supabase_client()
        
        # Normalize phone number - strip whitespace
        normalized = phone_number.strip()
        
        # Try exact match first
        phone_response = client.table("user_phone_numbers")\
            .select("user_id")\
            .eq("phone_number", normalized)\
            .eq("is_verified", True)\
            .limit(1)\
            .execute()
        
        # If not found, try with LIKE for partial matches (handles formatting differences)
        phone_data = extract_supabase_data(phone_response)
        if not phone_data:
            # Remove common separators and try again
            cleaned = normalized.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
            phone_response = client.table("user_phone_numbers")\
                .select("user_id, phone_number")\
                .eq("is_verified", True)\
                .execute()
            
            phone_data = extract_supabase_data(phone_response)
            # Manual matching on cleaned numbers
            if phone_data:
                for record in phone_data:
                    stored_phone = record.get('phone_number', '')
                    stored_cleaned = stored_phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
                    if cleaned == stored_cleaned:
                        return {'user_id': record['user_id']}
            
            return None
        
        user_id = phone_data[0]['user_id']
        
        # Return user_id in expected format
        return {'user_id': user_id}
    except Exception as e:
        logger.error(f"Error getting user by phone: {str(e)}", exc_info=True)
        return None


def get_coach_state(user_id: str) -> Optional[Dict[str, Any]]:
    """Get coach state for a user. Creates default if doesn't exist."""
    try:
        client = get_supabase_client()
        
        # Try to get existing state
        response = client.table("coach_state")\
            .select("*")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()
        
        result = get_first_item_or_none(response)
        if result:
            return result
        
        # Create default state if doesn't exist
        response = client.table("coach_state")\
            .insert({
                "user_id": user_id,
                "engagement_score": 50,
                "risk_state": "engaged"
            })\
            .execute()
        
        return get_first_item_or_none(response)
    except Exception as e:
        logger.error(f"Error getting/creating coach state: {str(e)}", exc_info=True)
        handle_supabase_error(e, "Failed to get coach state")
        return None


def update_coach_state(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update coach state for a user."""
    try:
        client = get_supabase_client()
        response = client.table("coach_state")\
            .update(updates)\
            .eq("user_id", user_id)\
            .execute()
        result = get_first_item_or_none(response, "Failed to update coach state")
        if result:
            return result
        raise DatabaseError("Failed to update coach state: No data returned")
    except DatabaseError:
        raise
    except Exception as e:
        handle_supabase_error(e, "Failed to update coach state")


def get_conversation_memory(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent conversation memory for a user (most recent first)."""
    try:
        client = get_supabase_client()
        response = client.table("messages")\
            .select("*")\
            .eq("userid", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        data = extract_supabase_data(response, default=[])
        # Reverse to get chronological order (oldest first)
        return list(reversed(data)) if data else []
    except Exception as e:
        logger.error(f"Error getting conversation memory: {str(e)}", exc_info=True)
        handle_supabase_error(e, "Failed to retrieve conversation memory")
        return []


def create_conversation_memory(
    user_id: str,
    message_text: str,
    direction: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Save a message to conversation memory."""
    import uuid
    try:
        client = get_supabase_client()
        
        # Generate unique chat_id for this message
        chat_id = str(uuid.uuid4())
        
        response = client.table("messages")\
            .insert({
                "chat_id": chat_id,                    # Primary key
                "userid": user_id,                     # Fixed: use 'userid' not 'user_id'
                "content": message_text,               # Fixed: use 'content' field
                "direction": direction,
                "sender_type": 'user' if direction == 'incoming' else 'gpt',
                "message_type": 'text',
                "read_in_app": False,
                "delivered": True,
                "metadata": metadata or {}
            })\
            .execute()
        result = get_first_item_or_none(response, "Failed to create conversation memory")
        if result:
            return result
        raise DatabaseError("Failed to create conversation memory: No data returned")
    except DatabaseError:
        raise
    except Exception as e:
        handle_supabase_error(e, "Failed to create conversation memory")


def get_user_preferences(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user preferences. Creates default if doesn't exist."""
    try:
        client = get_supabase_client()
        
        # Try to get existing preferences
        response = client.table("user_preferences")\
            .select("*")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()
        
        result = get_first_item_or_none(response)
        if result:
            return result
        
        # Create default preferences if doesn't exist
        response = client.table("user_preferences")\
            .insert({
                "user_id": user_id,
                "messaging_frequency": 3,
                "messaging_style": "balanced",
                "response_length": "medium",
                "quiet_hours_enabled": False,
                "quiet_hours_start": "22:00",
                "quiet_hours_end": "07:00",
                "quiet_hours_days": [0, 1, 2, 3, 4, 5, 6],
                "accountability_level": 5,
                "goals": [],
                "healthkit_enabled": False,
                "healthkit_sync_frequency": "daily"
            })\
            .execute()
        
        return get_first_item_or_none(response)
    except Exception as e:
        logger.error(f"Error getting/creating user preferences: {str(e)}", exc_info=True)
        handle_supabase_error(e, "Failed to get user preferences")
        return None


def update_user_preferences(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update user preferences."""
    try:
        client = get_supabase_client()
        response = client.table("user_preferences")\
            .update(updates)\
            .eq("user_id", user_id)\
            .execute()
        result = get_first_item_or_none(response, "Failed to update user preferences")
        if result:
            return result
        raise DatabaseError("Failed to update user preferences: No data returned")
    except DatabaseError:
        raise
    except Exception as e:
        handle_supabase_error(e, "Failed to update user preferences")


def get_journal_entries(user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Get journal entries for a user (most recent first)."""
    try:
        client = get_supabase_client()
        response = client.table("journal_entries")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .range(offset, offset + limit - 1)\
            .execute()
        return extract_supabase_data(response, default=[])
    except Exception as e:
        logger.error(f"Error getting journal entries: {str(e)}", exc_info=True)
        handle_supabase_error(e, "Failed to retrieve journal entries")
        return []


def create_journal_entry(user_id: str, entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a journal entry."""
    try:
        client = get_supabase_client()
        entry_data["user_id"] = user_id
        response = client.table("journal_entries")\
            .insert(entry_data)\
            .execute()
        result = get_first_item_or_none(response, "Failed to create journal entry")
        if result:
            return result
        raise DatabaseError("Failed to create journal entry: No data returned")
    except DatabaseError:
        raise
    except Exception as e:
        handle_supabase_error(e, "Failed to create journal entry")


def update_journal_entry(user_id: str, entry_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a journal entry."""
    try:
        client = get_supabase_client()
        response = client.table("journal_entries")\
            .update(updates)\
            .eq("id", entry_id)\
            .eq("user_id", user_id)\
            .execute()
        result = get_first_item_or_none(response, "Failed to update journal entry")
        if result:
            return result
        raise NotFoundError("Journal entry", entry_id)
    except NotFoundError:
        raise
    except Exception as e:
        handle_supabase_error(e, "Failed to update journal entry")


def delete_journal_entry(user_id: str, entry_id: str) -> bool:
    """Delete a journal entry."""
    try:
        client = get_supabase_client()
        response = client.table("journal_entries")\
            .delete()\
            .eq("id", entry_id)\
            .eq("user_id", user_id)\
            .execute()
        # Supabase delete returns empty data on success
        return True
    except Exception as e:
        logger.error(f"Error deleting journal entry: {str(e)}", exc_info=True)
        handle_supabase_error(e, "Failed to delete journal entry")
        return False


def get_journal_entry(user_id: str, entry_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific journal entry."""
    try:
        client = get_supabase_client()
        response = client.table("journal_entries")\
            .select("*")\
            .eq("id", entry_id)\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()
        return get_first_item_or_none(response)
    except Exception as e:
        logger.error(f"Error getting journal entry: {str(e)}", exc_info=True)
        return None

