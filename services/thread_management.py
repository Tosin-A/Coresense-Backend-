"""
Thread Management Service - Extracted from assistant_thread_service
Core thread lifecycle management for Assistant-Native architecture
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from openai import OpenAI
import uuid

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ThreadManagementService:
    """
    Core thread management service - handles thread lifecycle without context injection
    
    Features:
    - One thread per user (user_id -> thread_id mapping)
    - Thread creation and retrieval
    - Message addition and run execution
    - Function call handling
    - Thread status management
    """
    
    def __init__(self):
        from config import get_settings
        settings = get_settings()
        api_key = settings.openai_api_key
        
        if not api_key:
            logger.warning("OpenAI API key not found")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
            logger.info("OpenAI API client initialized")
        
        # The main coach assistant
        self.assistant_id = "asst_vb5GaGjEUo5REgjBrTYADHKf"
        
        # Function definitions for the assistant
        self.functions = [
            {
                "type": "function",
                "function": {
                    "name": "get_user_memory",
                    "description": "Retrieve stored user coaching memories and preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "memory_types": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "default": ["preferences", "goals", "patterns", "commitments"]
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "store_user_memory",
                    "description": "Store important coaching insights and user preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "memory_type": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "importance": {"type": "number", "default": 0.5}
                        },
                        "required": ["user_id", "memory_type", "title", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_conversation_pattern",
                    "description": "Analyze conversation for coaching insights",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "recent_messages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Recent conversation messages"
                            },
                            "analysis_type": {"type": "string"}
                        },
                        "required": ["user_id", "recent_messages"]
                    }
                }
            }
        ]
    
    async def get_or_create_user_thread(self, user_id: str) -> str:
        """
        Get existing thread or create new one for user.
        
        This is the CORE method - ensures one thread per user.
        """
        try:
            # Check if user already has a thread
            existing_thread_id = await self._get_user_thread_id(user_id)
            if existing_thread_id:
                logger.info(f"📌 Found existing thread for user {user_id}: {existing_thread_id}")
                return existing_thread_id
            
            # Create new thread
            logger.info(f"🆕 Creating new thread for user {user_id}")
            thread_id = await self._create_new_thread(user_id)
            
            # Store thread mapping
            await self._store_thread_mapping(user_id, thread_id)
            
            return thread_id
            
        except Exception as e:
            logger.error(f"Error getting/creating thread for user {user_id}: {e}")
            raise
    
    async def add_message_to_thread(self, thread_id: str, content: str, role: str = "user"):
        """Add message to existing thread"""
        if not self.client:
            raise Exception("OpenAI client not available")
        
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role=role,
            content=content
        )
    
    async def run_assistant(
        self, 
        thread_id: str, 
        user_id: str, 
        response_type: str,
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run assistant on thread with minimal instructions
        
        This is the MAIN method - minimal context, assistant handles memory.
        Note: We don't pass instructions here so the OpenAI Assistant's
        built-in system instructions (personality) are used instead.
        """
        try:
            if not self.client:
                raise Exception("OpenAI client not available")
            
            # Create and run - don't pass instructions so Assistant uses its system prompt
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id,
                instructions=None,  # Use Assistant's system instructions
                tools=self.functions
            )
            
            # Wait for completion
            return await self._wait_for_completion(run.id, thread_id)
            
        except Exception as e:
            logger.error(f"Error running assistant: {e}")
            return {
                "messages": ["I'm having trouble right now. Please try again."],
                "function_calls": [],
                "context_used": ["fallback"]
            }
    
    async def execute_function(self, user_id: str, function_name: str, arguments: Dict[str, Any]) -> bool:
        """Execute a specific function call"""
        try:
            if function_name == "get_user_memory":
                result = await self._execute_get_user_memory(arguments)
            elif function_name == "store_user_memory":
                result = await self._execute_store_user_memory(arguments)
            elif function_name == "analyze_conversation_pattern":
                result = await self._execute_analyze_pattern(arguments)
            else:
                logger.error(f"Unknown function: {function_name}")
                return False
            
            return result.get("success", False) if isinstance(result, dict) else True
            
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return False
    
    async def get_thread_status(self, user_id: str) -> Dict[str, Any]:
        """Get thread status for a user"""
        try:
            thread_id = await self.get_or_create_user_thread(user_id)
            
            return {
                "user_id": user_id,
                "thread_id": thread_id,
                "assistant_id": self.assistant_id,
                "status": "active",
                "has_persistent_memory": True
            }
            
        except Exception as e:
            logger.error(f"Error getting thread status: {e}")
            return {
                "user_id": user_id,
                "thread_id": None,
                "status": "error",
                "error": str(e)
            }
    
    # Private helper methods
    
    async def _get_user_thread_id(self, user_id: str) -> Optional[str]:
        """Get existing thread ID for user"""
        try:
            supabase = get_supabase_client()
            response = supabase.table("assistant_threads").select(
                "openai_thread_id, created_at"
            ).eq("user_id", user_id).eq("status", "active").execute()
            
            if response.data:
                # Return the most recent active thread
                thread_data = sorted(response.data, key=lambda x: x['created_at'], reverse=True)[0]
                return thread_data['openai_thread_id']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting thread ID for user {user_id}: {e}")
            return None
    
    async def _create_new_thread(self, user_id: str) -> str:
        """Create new OpenAI thread"""
        if not self.client:
            raise Exception("OpenAI client not available")
        
        thread = self.client.beta.threads.create()
        return thread.id
    
    async def _store_thread_mapping(self, user_id: str, thread_id: str):
        """Store user->thread mapping in database"""
        try:
            supabase = get_supabase_client()
            
            # Store thread mapping
            supabase.table("assistant_threads").insert({
                "user_id": user_id,
                "openai_thread_id": thread_id,
                "assistant_id": self.assistant_id,
                "status": "active",
                "created_at": datetime.now().isoformat()
            }).execute()
            
            logger.info(f"💾 Stored thread mapping: {user_id} -> {thread_id}")
            
        except Exception as e:
            logger.error(f"Error storing thread mapping: {e}")
            raise
    
    def _build_response_instructions(self, response_type: str) -> str:
        """Build minimal instructions based on response type"""
        instructions = {
            "greeting": "Give a brief, personalized greeting. Keep it under 20 words.",
            "check_in": "Ask a direct check-in question. Reference their streak if applicable.",
            "pressure": "Apply gentle pressure. Be direct but supportive.",
            "coaching": "Provide accountability coaching. Ask follow-up questions.",
            "celebration": "Acknowledge progress and build momentum.",
            "support": "Offer support and ask what they need.",
            "advice": "Provide specific coaching advice based on context.",
            "stats": "Provide coaching statistics and insights.",
            "insights": "Analyze patterns and provide coaching insights."
        }
        
        return instructions.get(response_type, "Provide helpful accountability coaching.")
    
    async def _wait_for_completion(self, run_id: str, thread_id: str) -> Dict[str, Any]:
        """Wait for run completion and handle function calls"""
        if not self.client:
            raise Exception("OpenAI client not available")
        
        while True:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            
            if run.status == "completed":
                return self._process_completed_run(thread_id, run_id)
            elif run.status == "requires_action":
                await self._handle_function_calls(run, thread_id)
            elif run.status in ["failed", "cancelled", "expired"]:
                raise Exception(f"Run failed: {run.status}")
            
            await self._sleep(1)
    
    async def _handle_function_calls(self, run, thread_id: str):
        """Handle function calls from assistant"""
        if not self.client:
            return
        
        if run.required_action and run.required_action.type == "submit_tool_outputs":
            tool_outputs = []
            
            for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                # Execute function
                if function_name == "get_user_memory":
                    result = await self._execute_get_user_memory(arguments)
                elif function_name == "store_user_memory":
                    result = await self._execute_store_user_memory(arguments)
                elif function_name == "analyze_conversation_pattern":
                    result = await self._execute_analyze_pattern(arguments)
                else:
                    result = {"error": f"Unknown function: {function_name}"}
                
                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(result)
                })
            
            # Submit outputs
            self.client.beta.threads.runs.submit_tool_outputs(
                run_id=run.id,
                thread_id=thread_id,
                tool_outputs=tool_outputs
            )
    
    async def _execute_get_user_memory(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute get_user_memory function"""
        try:
            supabase = get_supabase_client()
            user_id = arguments["user_id"]
            memory_types = arguments.get("memory_types", ["preferences", "goals", "patterns"])
            
            response = supabase.table("user_memories").select("*").eq(
                "user_id", user_id
            ).in_("memory_type", memory_types).execute()
            
            memories = []
            if response.data:
                for memory in response.data:
                    memories.append({
                        "type": memory["memory_type"],
                        "title": memory["title"],
                        "content": memory["content"],
                        "importance": memory.get("importance", 0.5)
                    })
            
            return {"memories": memories, "success": True}
            
        except Exception as e:
            logger.error(f"Error in get_user_memory: {e}")
            return {"memories": [], "success": False, "error": str(e)}
    
    async def _execute_store_user_memory(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute store_user_memory function"""
        try:
            supabase = get_supabase_client()
            user_id = arguments["user_id"]
            memory_type = arguments["memory_type"]
            title = arguments["title"]
            content = arguments["content"]
            importance = arguments.get("importance", 0.5)
            
            supabase.table("user_memories").insert({
                "user_id": user_id,
                "memory_type": memory_type,
                "title": title,
                "content": content,
                "importance": importance,
                "created_at": datetime.now().isoformat()
            }).execute()
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Error in store_user_memory: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_analyze_pattern(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute analyze_conversation_pattern function"""
        try:
            # Simple pattern analysis
            recent_messages = arguments.get("recent_messages", [])
            
            patterns = {
                "engagement_level": "high" if len(recent_messages) > 5 else "medium",
                "response_quality": "thoughtful" if any("?" in msg for msg in recent_messages) else "brief",
                "accountability_readiness": "high"
            }
            
            return {"patterns": patterns, "success": True}
            
        except Exception as e:
            logger.error(f"Error in analyze_conversation_pattern: {e}")
            return {"patterns": {}, "success": False, "error": str(e)}
    
    def _process_completed_run(self, thread_id: str, run_id: str) -> Dict[str, Any]:
        """
        Process completed run to extract ONLY new messages from this run.
        
        This fixes the "full-thread reload" problem by filtering messages
        to only return those generated in the current run.
        
        Args:
            thread_id: The OpenAI thread ID
            run_id: The current run ID to filter by
            
        Returns:
            Dict containing only new assistant messages from this run
        """
        if not self.client:
            raise Exception("OpenAI client not available")
        
        # List all messages from the thread
        all_messages = self.client.beta.threads.messages.list(thread_id=thread_id)
        
        assistant_messages = []
        function_calls = []
        
        for message in all_messages.data:
            # Filter: only process messages from the current run
            # OpenAI messages have a 'run_id' attribute that links them to a specific run
            if message.role == "assistant" and message.run_id == run_id:
                for content in message.content:
                    if content.type == "text":
                        assistant_messages.append({
                            "content": content.text.value,
                            "message_id": message.id
                        })
                    elif content.type == "tool_call":
                        function_calls.append({
                            "name": content.tool_call.function.name,
                            "arguments": content.tool_call.function.arguments
                        })
        
        # Extract just the text content for backward compatibility
        message_texts = [msg["content"] for msg in assistant_messages]
        
        logger.info(f"📋 Processed run {run_id}: Found {len(assistant_messages)} new assistant messages")
        
        return {
            "messages": message_texts,
            "message_details": assistant_messages,  # Include details for reconciliation
            "function_calls": function_calls,
            "run_id": run_id,
            "total_messages": len(all_messages.data),
            "new_messages_count": len(assistant_messages),
            "context_used": ["assistant_memory"]
        }
    
    async def _sleep(self, seconds: float):
        """Async sleep helper"""
        import asyncio
        await asyncio.sleep(seconds)


# Global thread management service instance
thread_management = ThreadManagementService()