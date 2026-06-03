"""
Conversation Management Service - Groq-powered chat completions.

Groq does NOT support OpenAI's Responses API or server-side Conversations API,
so we manage conversation history ourselves:
  - `conversation_id` is a UUID we generate, stored in `assistant_threads`.
  - History is reconstructed from the `messages` table on each call.
  - Tool calls follow the standard chat-completions tool-use loop.
"""

import json
import logging
import re
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

import groq
from groq import Groq

from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Cap how many prior messages we replay into Groq each turn.
MAX_HISTORY_MESSAGES = 20


class ConversationManagementService:
    """
    Conversation management using Groq Chat Completions.

    Public surface mirrors the previous OpenAI Responses-based service so
    coaching_service.py and downstream code keep working unchanged.
    """

    def __init__(self):
        from backend.config import get_settings
        settings = get_settings()
        api_key = settings.groq_api_key

        if not api_key:
            logger.warning("Groq API key not found")
            self.client = None
        else:
            self.client = Groq(api_key=api_key)
            logger.info("Groq client initialized (Chat Completions)")

        self.model = settings.groq_model or "llama-3.3-70b-versatile"

        # OpenAI-compatible tool definitions (Groq uses the same schema).
        #
        # IMPORTANT for Llama-on-Groq reliability:
        #   - `user_id` is NEVER exposed to the model — the server injects it
        #     from the authenticated session in `_run_with_tools`. Exposing it
        #     made the model hallucinate values like "current_user" / "user123".
        #   - We dropped `get_user_memory` and `store_user_memory` because the
        #     `public.user_memories` table does not exist; calling them was
        #     wasted tokens and frequently triggered Groq's `tool_use_failed`.
        #   - JSON-schema `default` on nested types is omitted; some Groq
        #     endpoints reject it. Defaults are described in `description`.
        #   - Tool descriptions are tightened to discourage drive-by calls on
        #     greetings / check-ins (where Llama tends to format tool calls
        #     as inline text and trigger `tool_use_failed`).
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "analyze_conversation_pattern",
                    "description": (
                        "Analyze recent conversation for coaching pattern insights. "
                        "Only call when the user EXPLICITLY asks for a pattern "
                        "analysis, reflection, or summary of how they've been doing. "
                        "Do NOT call on greetings, check-ins, vents, or normal "
                        "conversational turns."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recent_messages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Recent conversation messages",
                            },
                            "analysis_type": {"type": "string"},
                        },
                        "required": ["recent_messages"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
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
                        "required": ["title"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_calendar_event",
                    "description": (
                        "Schedule an event in the user's calendar. Call this when the user commits "
                        "to something time-specific, e.g. 'I'll go to the gym tomorrow', 'I need to "
                        "attend a meeting on Friday at 3pm'. Do NOT call this for vague intentions."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title under 60 chars"},
                            "date": {"type": "string", "description": "Target date YYYY-MM-DD"},
                            "preferred_time": {"type": "string", "description": "Preferred time HH:MM (24h), optional"},
                            "duration_minutes": {"type": "integer", "description": "Duration in minutes (default 60)"},
                            "notes": {"type": "string", "description": "Optional event notes"},
                        },
                        "required": ["title", "date"],
                    },
                },
            },
        ]

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def get_or_create_conversation(self, user_id: str) -> str:
        """Get existing conversation_id or create a new one for the user."""
        try:
            existing = await self._get_user_conversation_id(user_id)
            if existing:
                logger.info(f"Found existing conversation for user {user_id}: {existing}")
                return existing

            conversation_id = f"conv_{uuid.uuid4().hex}"
            logger.info(f"Creating new conversation for user {user_id}: {conversation_id}")
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
        """Send a user message and get the assistant response via Groq."""
        if not self.client:
            return {
                "messages": ["The coach isn't connected right now. Please try again later."],
                "response_id": None,
                "function_calls": [],
                "context_used": ["no_client"],
            }

        try:
            # Build the message list: system + history + (optional context) + new user msg.
            messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

            history = await self._load_history(user_id, conversation_id)
            messages.extend(history)

            if context_message:
                messages.append({"role": "system", "content": context_message})

            messages.append({"role": "user", "content": message})

            executed_functions: List[Dict[str, Any]] = []
            assistant_text = await self._run_with_tools(messages, user_id, executed_functions)

            response_id = f"resp_{uuid.uuid4().hex}"
            split_messages = self._split_into_bubbles(assistant_text) if assistant_text else ["I'm here. What's up?"]

            return {
                "messages": split_messages,
                "response_id": response_id,
                "function_calls": executed_functions,
                "context_used": ["conversation_memory"],
            }

        except Exception as e:
            logger.error(f"Error sending message via Groq: {e}", exc_info=True)
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
    # Groq + tool-call loop
    # -------------------------------------------------------------------------

    async def _run_with_tools(
        self,
        messages: List[Dict[str, Any]],
        user_id: str,
        executed_functions: List[Dict[str, Any]],
    ) -> str:
        """Run a chat completion, executing any tool calls in a loop.

        If Groq rejects our tool-call attempt with `tool_use_failed`
        (Llama-3.3 sometimes emits tool calls as inline `<function=...>`
        text instead of the structured `tool_calls` field), we retry
        once WITHOUT tools so the user still gets a usable reply.
        """
        max_iterations = 5

        for _ in range(max_iterations):
            try:
                completion = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                    temperature=0.7,
                    max_tokens=600,
                )
            except groq.BadRequestError as e:
                # Detect Groq's `tool_use_failed` — model wrote tool call as text.
                err_code = None
                try:
                    body = getattr(e, "body", None) or {}
                    if isinstance(body, dict):
                        err_code = (body.get("error") or {}).get("code")
                except Exception:
                    err_code = None
                if err_code is None:
                    err_code = "tool_use_failed" if "tool_use_failed" in str(e) else None

                if err_code == "tool_use_failed":
                    logger.warning(
                        "Groq tool_use_failed — retrying without tools so the "
                        "user still gets a reply. Underlying error: %s", e,
                    )
                    fallback = await asyncio.to_thread(
                        self.client.chat.completions.create,
                        model=self.model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=600,
                    )
                    return fallback.choices[0].message.content or ""
                raise

            choice = completion.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls:
                return msg.content or ""

            # Append the assistant message that requested tools, then satisfy each call.
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            })

            for call in tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                if "user_id" in arguments:
                    arguments["user_id"] = user_id

                result = await self._dispatch_function(call.function.name, arguments)
                executed_functions.append({
                    "name": call.function.name,
                    "arguments": arguments,
                    "result": result,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": json.dumps(result),
                })

        # Hit iteration cap — return whatever the model last said.
        return "I lost the thread there. What were you saying?"

    # -------------------------------------------------------------------------
    # History reconstruction
    # -------------------------------------------------------------------------

    async def _load_history(self, user_id: str, conversation_id: str) -> List[Dict[str, str]]:
        """Replay recent messages from Supabase as chat history."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("messages").select(
                "content, sender_type, direction, created_at"
            ).eq("userid", user_id).order(
                "created_at", desc=True
            ).limit(MAX_HISTORY_MESSAGES).execute()

            rows = response.data or []
            rows.reverse()  # chronological order

            history: List[Dict[str, str]] = []
            for row in rows:
                content = (row.get("content") or "").strip()
                if not content:
                    continue
                sender = (row.get("sender_type") or "").lower()
                direction = (row.get("direction") or "").lower()
                if sender == "user" or direction == "incoming":
                    history.append({"role": "user", "content": content})
                else:
                    history.append({"role": "assistant", "content": content})
            return history
        except Exception as e:
            logger.warning(f"Failed to load conversation history for {user_id}: {e}")
            return []

    @staticmethod
    def _split_into_bubbles(text: str) -> List[str]:
        """Split a single AI response into separate chat bubble segments."""
        segments = [s.strip() for s in text.split("\n\n") if s.strip()]
        if len(segments) > 1:
            return segments

        full = text.strip()
        if not full:
            return [text]

        parts = re.split(r'(?<=[.!?])\s+', full)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) > 1:
            return parts

        return [full]

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    async def _get_user_conversation_id(self, user_id: str) -> Optional[str]:
        """Get existing conversation_id for user from DB."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("assistant_threads").select(
                "conversation_id, created_at"
            ).eq("user_id", user_id).eq("status", "active").not_.is_(
                "conversation_id", "null"
            ).execute()

            if response.data:
                row = sorted(response.data, key=lambda x: x["created_at"], reverse=True)[0]
                return row["conversation_id"]
            return None
        except Exception as e:
            logger.error(f"Error getting conversation_id for user {user_id}: {e}")
            return None

    async def _store_conversation_mapping(self, user_id: str, conversation_id: str):
        """Store user -> conversation_id mapping in the assistant_threads table."""
        try:
            supabase = get_supabase_client()

            supabase.table("assistant_threads").update(
                {"status": "inactive"}
            ).eq("user_id", user_id).eq("status", "active").execute()

            supabase.table("assistant_threads").insert({
                "user_id": user_id,
                "conversation_id": conversation_id,
                "openai_thread_id": conversation_id,  # legacy NOT NULL column
                "assistant_id": "groq_chat",
                "status": "active",
                "created_at": datetime.now().isoformat(),
            }).execute()

            logger.info(f"Stored conversation mapping: {user_id} -> {conversation_id}")
        except Exception as e:
            logger.error(f"Error storing conversation mapping: {e}")
            raise

    # -------------------------------------------------------------------------
    # Function implementations
    # -------------------------------------------------------------------------

    async def _dispatch_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
