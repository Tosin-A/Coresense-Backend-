"""
Conversation Management Service - Responses API replacement for thread_management.py
Uses OpenAI Responses API + Conversations API instead of deprecated Assistants API.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

from openai import OpenAI

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ConversationManagementService:
    """
    Conversation management using OpenAI Responses API.

    Key differences from the old ThreadManagementService:
    - No polling. responses.create() returns synchronously.
    - Function calling is handled in a simple loop (no submit_tool_outputs).
    - Conversations API replaces threads for multi-turn context.
    - System prompt is passed inline (no separate Assistant object).
    """

    def __init__(self):
        from backend.config import get_settings
        settings = get_settings()
        api_key = settings.openai_api_key

        if not api_key:
            logger.warning("OpenAI API key not found")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized (Responses API)")

        self.model = settings.gpt_model or "gpt-4o-mini"

        # Tool definitions in Responses API flat format
        self.tools = [
            {
                "type": "function",
                "name": "get_user_memory",
                "description": "Retrieve stored user coaching memories and preferences",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "memory_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["preferences", "goals", "patterns"],
                        },
                    },
                    "required": ["user_id"],
                },
            },
            {
                "type": "function",
                "name": "store_user_memory",
                "description": "Store important coaching insights and user preferences",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "memory_type": {"type": "string"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "importance": {"type": "number", "default": 0.5},
                    },
                    "required": ["user_id", "memory_type", "title", "content"],
                },
            },
            {
                "type": "function",
                "name": "analyze_conversation_pattern",
                "description": "Analyze conversation for coaching insights",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "recent_messages": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Recent conversation messages",
                        },
                        "analysis_type": {"type": "string"},
                    },
                    "required": ["user_id", "recent_messages"],
                },
            },
            {
                "type": "function",
                "name": "create_user_task",
                "description": (
                    "Create a task on the user's to-do list. Call this ONLY when the user makes "
                    "a clear, specific commitment to do something actionable. Examples: 'I'll go to "
                    "the gym tomorrow at 6am', 'I'm going to read for 30 minutes tonight', 'I need "
                    "to finish my report by Friday'. Do NOT call this for vague intentions like "
                    "'I should exercise more' or 'I want to be healthier'. The commitment must have "
                    "a specific action."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "The user's ID",
                        },
                        "title": {
                            "type": "string",
                            "description": "Short, actionable task title under 60 characters",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional additional context about the task",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Task priority. Default to medium.",
                        },
                        "coach_reasoning": {
                            "type": "string",
                            "description": (
                                "Write in first person from the user's perspective "
                                "(e.g. \"I'm working on robotics at 4\", \"I'm going to the gym at 6am\"). "
                                "Keep it to one short sentence."
                            ),
                        },
                    },
                    "required": ["user_id", "title"],
                },
            },
            {
                "type": "function",
                "name": "schedule_calendar_event",
                "description": (
                    "Schedule an event in the user's calendar. Call this when the user commits "
                    "to something time-specific, e.g. 'I'll go to the gym tomorrow', 'I need to "
                    "attend a meeting on Friday at 3pm'. Do NOT call this for vague intentions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "title": {"type": "string", "description": "Event title under 60 chars"},
                        "date": {"type": "string", "description": "Target date YYYY-MM-DD"},
                        "preferred_time": {"type": "string", "description": "Preferred time HH:MM (24h), optional"},
                        "duration_minutes": {"type": "integer", "description": "Duration in minutes, default 60", "default": 60},
                        "notes": {"type": "string", "description": "Optional event notes"},
                    },
                    "required": ["user_id", "title", "date"],
                },
            },
        ]

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def get_or_create_conversation(self, user_id: str) -> str:
        """
        Get existing conversation_id or create a new one for the user.
        Falls back to creating a fresh conversation if none exists.
        """
        try:
            existing = await self._get_user_conversation_id(user_id)
            if existing:
                logger.info(f"Found existing conversation for user {user_id}: {existing}")
                return existing

            logger.info(f"Creating new conversation for user {user_id}")
            conversation_id = await self._create_new_conversation(user_id)
            await self._store_conversation_mapping(user_id, conversation_id)
            return conversation_id

        except Exception as e:
            logger.error(f"Error getting/creating conversation for user {user_id}: {e}")
            raise

    async def send_message(
        self,
        conversation_id: str,
        user_id: str,
        message: str,
        system_prompt: str,
        context_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a user message and get the assistant response.
        Single synchronous call — no polling needed.
        """
        if not self.client:
            raise Exception("OpenAI client not available")

        try:
            input_messages = []

            # Optionally prepend context
            if context_message:
                input_messages.append({"role": "user", "content": context_message})

            input_messages.append({"role": "user", "content": message})

            # Single synchronous call
            response = await asyncio.to_thread(
                self.client.responses.create,
                model=self.model,
                instructions=system_prompt,
                input=input_messages,
                tools=self.tools,
                conversation={"id": conversation_id},
                store=True,
            )

            # Handle any function calls in a loop
            executed_functions = []
            response = await self._handle_tool_calls(response, user_id, executed_functions)

            # Extract text messages from response
            messages = self._extract_messages(response)

            return {
                "messages": messages,
                "response_id": response.id,
                "function_calls": executed_functions,
                "context_used": ["conversation_memory"],
            }

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {
                "messages": ["I'm having trouble right now. Please try again."],
                "response_id": None,
                "function_calls": [],
                "context_used": ["fallback"],
            }

    async def execute_function(self, user_id: str, function_name: str, arguments: Dict[str, Any]) -> bool:
        """Execute a specific function call (for external callers)."""
        try:
            result = await self._dispatch_function(function_name, arguments)
            return result.get("success", False) if isinstance(result, dict) else True
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return False

    async def get_conversation_status(self, user_id: str) -> Dict[str, Any]:
        """Get conversation status for a user."""
        try:
            conversation_id = await self.get_or_create_conversation(user_id)
            return {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "status": "active",
                "has_persistent_memory": True,
            }
        except Exception as e:
            logger.error(f"Error getting conversation status: {e}")
            return {
                "user_id": user_id,
                "conversation_id": None,
                "status": "error",
                "error": str(e),
            }

    # -------------------------------------------------------------------------
    # Tool call loop
    # -------------------------------------------------------------------------

    async def _handle_tool_calls(
        self, response, user_id: str, executed_functions: List[Dict[str, Any]]
    ):
        """
        Process function calls from the response in a loop.
        Each iteration submits tool outputs and gets the next response.
        """
        if not self.client:
            return response

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            fn_calls = [item for item in response.output if item.type == "function_call"]
            if not fn_calls:
                break

            iteration += 1
            outputs = []

            for call in fn_calls:
                arguments = json.loads(call.arguments)

                # Override user_id with the real one
                if "user_id" in arguments:
                    arguments["user_id"] = user_id

                result = await self._dispatch_function(call.name, arguments)

                executed_functions.append({
                    "name": call.name,
                    "arguments": arguments,
                    "result": result,
                })

                outputs.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                })

            # Continue the conversation with tool outputs
            response = await asyncio.to_thread(
                self.client.responses.create,
                model=self.model,
                input=outputs,
                previous_response_id=response.id,
                tools=self.tools,
                store=True,
            )

        return response

    # -------------------------------------------------------------------------
    # Message extraction
    # -------------------------------------------------------------------------

    def _extract_messages(self, response) -> List[str]:
        """Extract text messages from a Responses API response."""
        messages = []
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        messages.append(content.text)
        return messages if messages else ["I'm here. What's up?"]

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    async def _get_user_conversation_id(self, user_id: str) -> Optional[str]:
        """Get existing conversation_id for user from DB."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("assistant_threads").select(
                "conversation_id, created_at"
            ).eq("user_id", user_id).eq("status", "active").not_.is_("conversation_id", "null").execute()

            if response.data:
                row = sorted(response.data, key=lambda x: x["created_at"], reverse=True)[0]
                return row["conversation_id"]
            return None
        except Exception as e:
            logger.error(f"Error getting conversation_id for user {user_id}: {e}")
            return None

    async def _create_new_conversation(self, user_id: str) -> str:
        """Create a new OpenAI conversation via the Conversations API."""
        if not self.client:
            raise Exception("OpenAI client not available")

        conversation = await asyncio.to_thread(self.client.conversations.create)
        return conversation.id

    async def _store_conversation_mapping(self, user_id: str, conversation_id: str):
        """Store user → conversation_id mapping in the assistant_threads table."""
        try:
            supabase = get_supabase_client()

            # Deactivate any old rows for this user
            supabase.table("assistant_threads").update(
                {"status": "inactive"}
            ).eq("user_id", user_id).eq("status", "active").execute()

            # Insert new mapping
            supabase.table("assistant_threads").insert({
                "user_id": user_id,
                "conversation_id": conversation_id,
                "openai_thread_id": conversation_id,  # backwards compat column
                "assistant_id": "responses_api",  # placeholder for NOT NULL constraint
                "status": "active",
                "created_at": datetime.now().isoformat(),
            }).execute()

            logger.info(f"Stored conversation mapping: {user_id} -> {conversation_id}")
        except Exception as e:
            logger.error(f"Error storing conversation mapping: {e}")
            raise

    # -------------------------------------------------------------------------
    # Function implementations (unchanged from thread_management)
    # -------------------------------------------------------------------------

    async def _dispatch_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Route a function call to its implementation."""
        handlers = {
            "get_user_memory": self._execute_get_user_memory,
            "store_user_memory": self._execute_store_user_memory,
            "analyze_conversation_pattern": self._execute_analyze_pattern,
            "create_user_task": self._execute_create_user_task,
            "schedule_calendar_event": self._execute_schedule_calendar_event,
        }
        handler = handlers.get(function_name)
        if not handler:
            logger.error(f"Unknown function: {function_name}")
            return {"error": f"Unknown function: {function_name}"}
        return await handler(arguments)

    async def _execute_get_user_memory(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
                        "importance": memory.get("importance", 0.5),
                    })
            return {"memories": memories, "success": True}
        except Exception as e:
            logger.error(f"Error in get_user_memory: {e}")
            return {"memories": [], "success": False, "error": str(e)}

    async def _execute_store_user_memory(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            supabase = get_supabase_client()
            supabase.table("user_memories").insert({
                "user_id": arguments["user_id"],
                "memory_type": arguments["memory_type"],
                "title": arguments["title"],
                "content": arguments["content"],
                "importance": arguments.get("importance", 0.5),
                "created_at": datetime.now().isoformat(),
            }).execute()
            return {"success": True}
        except Exception as e:
            logger.error(f"Error in store_user_memory: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_analyze_pattern(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            recent_messages = arguments.get("recent_messages", [])
            patterns = {
                "engagement_level": "high" if len(recent_messages) > 5 else "medium",
                "response_quality": "thoughtful" if any("?" in msg for msg in recent_messages) else "brief",
                "accountability_readiness": "high",
            }
            return {"patterns": patterns, "success": True}
        except Exception as e:
            logger.error(f"Error in analyze_conversation_pattern: {e}")
            return {"patterns": {}, "success": False, "error": str(e)}

    async def _execute_create_user_task(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            supabase = get_supabase_client()
            user_id = arguments["user_id"]
            title = arguments["title"]
            priority = arguments.get("priority", "medium")
            if priority not in ("low", "medium", "high", "urgent"):
                priority = "medium"

            now = datetime.now().isoformat()
            todo_data = {
                "user_id": user_id,
                "title": title,
                "created_by": "coach",
                "status": "pending",
                "priority": priority,
                "created_at": now,
                "updated_at": now,
            }
            if arguments.get("description"):
                todo_data["description"] = arguments["description"]
            if arguments.get("coach_reasoning"):
                todo_data["coach_reasoning"] = arguments["coach_reasoning"]

            response = supabase.table("shared_todos").insert(todo_data).execute()

            if response.data and len(response.data) > 0:
                created = response.data[0]
                logger.info(f"Created coach task '{title}' for user {user_id}")
                return {
                    "success": True,
                    "task_id": created["id"],
                    "title": title,
                    "message": f"Task '{title}' has been added to the user's to-do list.",
                }
            return {"success": False, "error": "Failed to insert task"}
        except Exception as e:
            logger.error(f"Error in create_user_task: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_schedule_calendar_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "action": "schedule_calendar_event",
            "event_data": {
                "title": arguments.get("title"),
                "date": arguments.get("date"),
                "preferred_time": arguments.get("preferred_time"),
                "duration_minutes": arguments.get("duration_minutes", 60),
                "notes": arguments.get("notes"),
            },
        }


# Global instance
conversation_management = ConversationManagementService()
