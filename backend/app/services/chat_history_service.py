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
            # 2. Check if Mock LLM mode is active or Gemini Key is missing
            if settings.ALLOW_MOCK_LLM or not settings.GEMINI_API_KEY or "placeholder" in settings.GEMINI_API_KEY.lower():
                title = user_query[:50] + "..." if len(user_query) > 50 else user_query
            else:
                try:
                    from app.core.gemini_gate import check_gemini_cooldown, set_gemini_cooldown, parse_retry_delay
                    if await check_gemini_cooldown():
                        logger.warning("GeminiGate: Gemini is in cooldown. Skipping session title generation.")
                    else:
                        # 3. Call Gemini to generate a short summary title
                        from langchain_google_genai import ChatGoogleGenerativeAI
                        llm = ChatGoogleGenerativeAI(
                            google_api_key=settings.GEMINI_API_KEY,
                            model=settings.GEMINI_MODEL,
                            temperature=0,
                            max_retries=1
                        )
                        prompt = (
                            "Generate a extremely short, concise conversational title (max 5 words) summarizing "
                            f"this user query: '{user_query}' and the assistant response. Do not use quotes, punctuation or prefix text."
                        )
                        resp = await llm.ainvoke(prompt)
                        title = resp.content.strip().strip('"').strip("'").strip()
                except Exception as e:
                    if "resourceexhausted" in str(e).lower() or "429" in str(e).lower() or "rate_limit" in str(e).lower() or "quota" in str(e).lower():
                        try:
                            delay = parse_retry_delay(e)
                            await set_gemini_cooldown(delay)
                        except Exception as gate_err:
                            logger.error(f"ChatHistoryService: Failed to set Gemini cooldown gate: {gate_err}")
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
            # Fetch the latest user query in this session
            try:
                stmt = (
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id, ChatMessage.role == ChatRole.user)
                    .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                )
                res = await self.db.execute(stmt)
                user_msg = res.scalars().first()
                user_query = user_msg.content if user_msg else "Chat Session"
                
                # Launch background title summary task without blocking the response
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
