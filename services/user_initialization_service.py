"""
User Initialization Service
Handles initialization of user data when new users sign up
"""

from typing import Dict, Any, Optional
import logging
from datetime import datetime

from backend.database.supabase_client import get_supabase_client
from .message_limit_service import get_user_message_limit

logger = logging.getLogger(__name__)

def initialize_new_user(user_id: str, user_email: str = None, full_name: str = None) -> Dict[str, Any]:
    """
    Initialize all necessary data for a new user.
    
    Args:
        user_id: The new user's ID
        user_email: User's email address (optional)
        full_name: User's full name (optional)
        
    Returns:
        Dict with initialization results
    """
    results = {
        'user_id': user_id,
        'success': True,
        'errors': [],
        'initialized': []
    }
    
    try:
        # 1. Initialize message limits
        try:
            limits = get_user_message_limit(user_id)
            results['initialized'].append('message_limits')
            logger.info(f"✅ Initialized message limits for user {user_id}")
        except Exception as e:
            error_msg = f"Failed to initialize message limits: {e}"
            results['errors'].append(error_msg)
            logger.error(f"❌ {error_msg}")
        
        # 2. Initialize user profile in public.users table if needed
        try:
            client = get_supabase_client()
            
            # Check if user profile exists
            profile_check = client.table("users").select("*").eq("id", user_id).limit(1).execute()
            
            if not profile_check.data:
                # Create user profile
                profile_data = {
                    "id": user_id,
                    "email": user_email or "",
                    "full_name": full_name,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                profile_result = client.table("users").insert(profile_data).execute()
                
                if profile_result.data:
                    results['initialized'].append('user_profile')
                    logger.info(f"✅ Created user profile for {user_id}")
                else:
                    error_msg = "Failed to create user profile - no data returned"
                    results['errors'].append(error_msg)
                    logger.error(f"❌ {error_msg}")
            else:
                results['initialized'].append('user_profile_existed')
                logger.info(f"✅ User profile already exists for {user_id}")
                
        except Exception as e:
            error_msg = f"Failed to initialize user profile: {e}"
            results['errors'].append(error_msg)
            logger.error(f"❌ {error_msg}")
        
        # 3. Initialize other user-specific data as needed
        # (Add more initializations here as the app grows)
        
        # Determine overall success
        if results['errors']:
            results['success'] = False
            
        logger.info(f"🏁 User initialization complete for {user_id}: {len(results['initialized'])} initialized, {len(results['errors'])} errors")
        
    except Exception as e:
        error_msg = f"Unexpected error during user initialization: {e}"
        results['errors'].append(error_msg)
        results['success'] = False
        logger.error(f"❌ {error_msg}", exc_info=True)
    
    return results

def initialize_user_message_limits_only(user_id: str) -> bool:
    """
    Initialize only the message limits for a user.
    Simpler function for when you just need to ensure message limits exist.
    
    Args:
        user_id: User ID to initialize limits for
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        limits = get_user_message_limit(user_id)
        logger.info(f"✅ Message limits initialized for user {user_id}: {limits}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize message limits for user {user_id}: {e}")
        return False

# Test function
if __name__ == "__main__":
    # Test with a sample user ID
    test_user_id = "c18f7b13-6d6a-42d6-ac2e-c67cf90e1d1e"
    result = initialize_new_user(test_user_id, "test@example.com", "Test User")
    print(f"Initialization result: {result}")