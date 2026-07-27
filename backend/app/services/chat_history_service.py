import uuid
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models.chat import ChatSession, ChatMessage, ChatRole
from app.core.config import settings
from app.core.cache import cache
from app.db.session import SessionLocal


async def _generate_and_save_title(session_id: uuid.UUID, user_query: str, assistant_response: str) -> None:
    """
    Background fire-and-forget task to generate a short title for a chat session.
    Only executes if the title is not already set.
    """
    async with SessionLocal() as db:
        try:
            # 1. Fetch ChatSession to verify if title is already set
            stmt = select(ChatSession).where(ChatSession.id == session_id)
            res = await db.execute(stmt)
            session = res.scalars().first()
            if not session or session.title:
                return

            title = None
            # 2. Check if Mock LLM mode is active or OpenRouter Key is missing
            openrouter_key = settings.OPENROUTER_API_KEY or ""
            if settings.ALLOW_MOCK_LLM or not openrouter_key or "placeholder" in openrouter_key.lower():
                title = user_query[:50] + "..." if len(user_query) > 50 else user_query
            else:
                try:
                    from app.core.openrouter_client import openrouter_chat
                    prompt = (
                        "Generate an extremely short, concise conversational title (max 5 words) summarizing "
                        f"this user query: '{user_query}'. Do not use quotes, punctuation or prefix text."
                    )
                    llm_res = await openrouter_chat(
                        messages=[{"role": "user", "content": prompt}],
                        model=settings.OPENROUTER_MODEL,
                        api_key=settings.OPENROUTER_API_KEY,
                        timeout=15.0
                    )
                    title = llm_res.content.strip().strip('"').strip("'").strip()
                except Exception as e:
                    logger.warning(f"Failed to generate session title via LLM: {e}")

            # Fallback to query prefix if generation was unsuccessful
            if not title:
                title = user_query[:50] + "..." if len(user_query) > 50 else user_query

            session.title = title
            db.add(session)
            await db.commit()
            logger.info(f"Background title generated successfully for session {session_id}: {title}")
        except Exception as e:
            logger.error(f"Failed in title generation background task for session {session_id}: {e}")


class ChatHistoryService:
    """
    Service class managing conversation histories, message persistence,
    and cache-backed token-bounded context construction.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, ticker: Optional[str] = None) -> ChatSession:
        """Create a new ChatSession and persist it."""
        session = ChatSession(ticker=ticker)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def save_turn(
        self,
        session_id: uuid.UUID,
        user_query: str,
        assistant_response: Any,
        user_metadata: Optional[dict] = None
    ) -> tuple[ChatMessage, ChatMessage]:
        """
        Persists a complete conversational turn (User message + Assistant response)
        atomically in a single database transaction.
        Handles string responses or AIResponse pydantic models gracefully.
        """
        # Invalidate Redis context cache for this session
        cache_key = f"chat:context:{session_id}"
        await cache.delete(cache_key)

        # 1. Prepare user message
        user_msg = ChatMessage(
            session_id=session_id,
            role=ChatRole.user,
            content=user_query,
            metadata_=user_metadata
        )
        self.db.add(user_msg)

        # 2. Extract content and metadata for assistant response
        ast_content = ""
        ast_metadata = None

        if hasattr(assistant_response, "executive_summary"):
            exec_summary = getattr(assistant_response, "executive_summary", "") or ""
            key_insights = getattr(assistant_response, "key_insights", []) or []
            is_degraded = getattr(assistant_response, "is_degraded", False)
            error_type = getattr(assistant_response, "error_type", None)
            
            # Clean user-facing text fallback if parsing failed
            if is_degraded and error_type == "json_parse_failure":
                ast_content = "I had trouble generating a clean summary for this query. Please try rephrasing or asking again."
            elif exec_summary.strip() and not (is_degraded and "could not be parsed" in exec_summary.lower()):
                ast_content = exec_summary.strip()
            elif key_insights:
                ast_content = "\n".join(str(k) for k in key_insights)
            else:
                ast_content = "Response generated successfully."

            if hasattr(assistant_response, "model_dump"):
                try:
                    ast_metadata = assistant_response.model_dump()
                    if is_degraded:
                        ast_metadata["is_error"] = True
                except Exception as dump_err:
                    logger.warning(f"Failed to dump AIResponse metadata: {dump_err}")
        elif isinstance(assistant_response, dict):
            ast_content = assistant_response.get("executive_summary") or assistant_response.get("content") or str(assistant_response)
            ast_metadata = assistant_response
        else:
            ast_content = str(assistant_response)

        ast_msg = ChatMessage(
            session_id=session_id,
            role=ChatRole.assistant,
            content=ast_content,
            metadata_=ast_metadata
        )
        self.db.add(ast_msg)

        # Atomic commit for both user and assistant messages
        await self.db.commit()
        await self.db.refresh(user_msg)
        await self.db.refresh(ast_msg)

        # Trigger background title generation
        try:
            asyncio.create_task(_generate_and_save_title(session_id, user_query, ast_content))
        except Exception as e:
            logger.error(f"Failed to trigger background title generator: {e}")

        return user_msg, ast_msg

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> ChatMessage:
        """
        Add a message to the database, invalidate Redis context cache,
        and schedule title generation if applicable.
        """
        # Invalidate build_context_window Redis cache for this session
        cache_key = f"chat:context:{session_id}"
        await cache.delete(cache_key)

        message = ChatMessage(
            session_id=session_id,
            role=ChatRole(role),
            content=content,
            metadata_=metadata
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        # Trigger fire-and-forget title generation if this is the assistant reply
        if role == "assistant":
            try:
                stmt = (
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id, ChatMessage.role == ChatRole.user)
                    .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                )
                res = await self.db.execute(stmt)
                user_msg = res.scalars().first()
                user_query = user_msg.content if user_msg else "Chat Session"
                asyncio.create_task(_generate_and_save_title(session_id, user_query, content))
            except Exception as e:
                logger.error(f"Failed to trigger background title generator: {e}")

        return message

    async def get_recent_messages(self, session_id: uuid.UUID, limit: int = 20) -> List[ChatMessage]:
        """
        Retrieve recent messages for a session, ordered chronologically
        (sorting by created_at then id as a secondary key).
        """
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        messages = list(res.scalars().all())
        
        # Sort in chronological order (oldest first)
        messages.sort(key=lambda m: (m.created_at, m.id))
        return messages

    async def build_context_window(self, session_id: uuid.UUID, max_tokens: int = 4000) -> List[Dict[str, Any]]:
        """
        Constructs context window messages for the session up to max_tokens,
        caching the final formatted list to Redis for 60s.
        """
        cache_key = f"chat:context:{session_id}"
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT for context window on session: {session_id}")
            return cached

        logger.debug(f"Cache MISS for context window on session: {session_id}")
        
        # Fetch all messages newest-first
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        )
        res = await self.db.execute(stmt)
        messages = list(res.scalars().all())

        selected_messages = []
        total_tokens = 0

        # Locate the most recent system message in the thread
        recent_system = None
        for msg in messages:
            if msg.role == ChatRole.system:
                recent_system = msg
                break

        recent_system_tokens = 0
        if recent_system:
            recent_system_tokens = len(recent_system.content) / 4

        # Iterate descending and accumulate up to the max_tokens budget (minus reserved system tokens)
        for msg in messages:
            if recent_system and msg.id == recent_system.id:
                continue

            t_tokens = len(msg.content) / 4
            budget_limit = max_tokens - recent_system_tokens
            if total_tokens + t_tokens <= budget_limit:
                selected_messages.append(msg)
                total_tokens += t_tokens
            else:
                break

        # Re-inject the most recent system message if it exists
        if recent_system:
            selected_messages.append(recent_system)

        # Sort back to chronological order (oldest first)
        selected_messages.sort(key=lambda m: (m.created_at, m.id))

        # Format into Anthropic/API spec list of dicts
        formatted = [{"role": msg.role.value, "content": msg.content} for msg in selected_messages]

        # Cache the results to Redis for 60 seconds
        await cache.set(cache_key, formatted, ttl=60)
        return formatted
