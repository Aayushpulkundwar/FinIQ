"""
app/core/ollama_client.py

.. deprecated::
    LLM generation (chat/generate) via this module has been replaced by
    ``app.core.openrouter_client``.  The Ollama server is now used ONLY for
    embedding generation (``/api/embed``) via ``app.rag.embeddings``.

    This file is kept for reference and potential future local-inference use.
    Do NOT import ``ollama_chat`` or ``ollama_generate`` for production LLM
    generation paths — use ``openrouter_chat`` from ``openrouter_client`` instead.

Shared async and sync HTTP helpers for the Ollama local inference server.

- ollama_chat()      - async; calls /api/chat (DEPRECATED for generation — use openrouter_chat).
- ollama_generate()  - async; calls /api/generate (DEPRECATED for generation).
- ollama_chat_sync() - sync;  calls /api/chat (DEPRECATED for generation — use openrouter_chat_sync).

All functions raise on non-2xx HTTP status or connection errors so callers
can distinguish Ollama failures from successful empty responses.
"""
from __future__ import annotations

from typing import List, Dict

import httpx
from loguru import logger


# ---------------------------------------------------------------------------
# Async variants - use in FastAPI / asyncio contexts
# ---------------------------------------------------------------------------

async def ollama_chat(
    messages: List[Dict[str, str]],
    model: str,
    base_url: str,
    timeout: float = 120.0,
) -> str:
    """
    Calls Ollama /api/chat with a list of role-content message dicts.
    Returns the assistant message content string.
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": 8192
        }
    }
    logger.debug(f"OllamaClient: POST {url} model={model} messages={len(messages)}")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    try:
        content: str = data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"OllamaClient: Unexpected /api/chat response structure: {data}"
        ) from exc

    logger.debug(f"OllamaClient: /api/chat response length={len(content)}")
    return content


async def ollama_generate(
    prompt: str,
    model: str,
    base_url: str,
    timeout: float = 120.0,
) -> str:
    """
    Calls Ollama /api/generate with a single prompt string.
    Prefer ollama_chat() when the model supports chat format.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 8192
        }
    }
    logger.debug(f"OllamaClient: POST {url} model={model} prompt_len={len(prompt)}")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    try:
        content: str = data["response"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"OllamaClient: Unexpected /api/generate response structure: {data}"
        ) from exc

    logger.debug(f"OllamaClient: /api/generate response length={len(content)}")
    return content


# ---------------------------------------------------------------------------
# Sync variant - use in Celery tasks / synchronous call sites
# ---------------------------------------------------------------------------

def ollama_chat_sync(
    messages: List[Dict[str, str]],
    model: str,
    base_url: str,
    timeout: float = 120.0,
) -> str:
    """
    Synchronous version of ollama_chat() for use in Celery workers or
    other non-async call sites.
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": 8192
        }
    }
    logger.debug(f"OllamaClient(sync): POST {url} model={model} messages={len(messages)}")
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    try:
        content: str = data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"OllamaClient(sync): Unexpected /api/chat response structure: {data}"
        ) from exc

    logger.debug(f"OllamaClient(sync): /api/chat response length={len(content)}")
    return content
