"""
app/core/openrouter_client.py

Async HTTP helper for the OpenRouter hosted LLM API with automatic local
Ollama fallback.

OpenRouter exposes an OpenAI-compatible chat completions endpoint, so the
wire format is identical to OpenAI's /v1/chat/completions.

Public surface:
  openrouter_chat(messages, model, api_key, base_url, timeout) -> LLMResult
  openrouter_chat_sync(messages, model, api_key, base_url, timeout) -> LLMResult

Both functions return an ``LLMResult`` namedtuple with two fields:
  content      : str   — the assistant reply text
  provider_used: str   — "openrouter" | "ollama_fallback"

Retry / Fallback policy:
  1. Single automatic retry on 5xx / connect / timeout errors (transient).
  2. Immediate PermissionError on 401 / 403 (bad credentials — no retry,
     no Ollama fallback because the issue is auth, not availability).
  3. On 429 (rate-limit) or on *all* transient errors exhausting retries:
     fall back to local Ollama using settings.OLLAMA_MODEL and
     settings.OLLAMA_BASE_URL.  The Ollama call uses the same message list
     so the caller receives a semantically equivalent reply.

Required headers (per OpenRouter docs):
  Authorization: Bearer {api_key}
  HTTP-Referer: https://finsightai.app   (identifies the calling app)
  X-Title: FinsightAI                    (display name in OpenRouter dashboard)
"""
from __future__ import annotations

import asyncio
import time
from typing import List, Dict, NamedTuple, Optional

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_HTTP_REFERER = "https://finsightai.app"
_APP_TITLE = "FinsightAI"

# HTTP status codes that should NOT be retried (auth / permission errors).
_AUTH_STATUS_CODES = {401, 403}

# HTTP status codes that are transient and warrant a single retry.
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class LLMResult(NamedTuple):
    """Carries the generated text alongside which provider served it."""
    content: str
    provider_used: str  # "openrouter" | "ollama_fallback"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": _HTTP_REFERER,
        "X-Title": _APP_TITLE,
        "Content-Type": "application/json",
    }


def _trim_prompt_for_ollama(messages: List[Dict[str, str]], target_chars: int = 22000) -> List[Dict[str, str]]:
    """
    Trims the prompt to fit comfortably within Ollama's 8192-token context window
    by capping retrieved chunks and long financial strings in the user message.
    Target length is set in characters (~22000 chars is roughly 5500 tokens).
    """
    import re
    import json

    trimmed = [dict(m) for m in messages]
    if len(trimmed) < 2:
        return trimmed

    system_content = trimmed[0]["content"]
    user_content = trimmed[1]["content"]

    total_len = len(system_content) + len(user_content)
    if total_len <= target_chars:
        return trimmed

    logger.info(
        f"Ollama prompt size ({total_len} chars) exceeds budget ({target_chars} chars). Trimming context..."
    )

    # 1. Trim comparison chunks
    if "Retrieved Context for Company A:" in user_content:
        parts = re.split(
            r'(Retrieved Context for Company A:\n|Retrieved Context for Company B:\n)',
            user_content
        )
        if len(parts) >= 5:
            # Trim A-chunks to top 2
            a_chunks = re.split(r'(A-Chunk \d+:)', parts[2])
            trimmed_a = a_chunks[0]
            chunk_count = 0
            for idx in range(1, len(a_chunks), 2):
                if chunk_count >= 2:
                    break
                trimmed_a += a_chunks[idx] + a_chunks[idx+1]
                chunk_count += 1
            parts[2] = trimmed_a + "[... remaining A-chunks trimmed for local model context limit ...]\n\n"

            # Trim B-chunks to top 2
            b_chunks = re.split(r'(B-Chunk \d+:)', parts[4])
            trimmed_b = b_chunks[0]
            chunk_count = 0
            for idx in range(1, len(b_chunks), 2):
                if chunk_count >= 2:
                    break
                trimmed_b += b_chunks[idx] + b_chunks[idx+1]
                chunk_count += 1
            parts[4] = trimmed_b + "[... remaining B-chunks trimmed for local model context limit ...]\n\n"

            user_content = "".join(parts)

    # 2. Trim single-company chunks
    elif "Retrieved Context:" in user_content:
        parts = re.split(r'(Retrieved Context:\n)', user_content)
        if len(parts) >= 3:
            chunks = re.split(r'(Chunk \d+:)', parts[2])
            trimmed_chunks = chunks[0]
            chunk_count = 0
            for idx in range(1, len(chunks), 2):
                if chunk_count >= 2:
                    break
                trimmed_chunks += chunks[idx] + chunks[idx+1]
                chunk_count += 1
            parts[2] = trimmed_chunks + "[... remaining chunks trimmed for local model context limit ...]\n\n"
            user_content = "".join(parts)

    total_len = len(system_content) + len(user_content)
    if total_len <= target_chars:
        trimmed[1]["content"] = user_content
        logger.info(f"Ollama prompt trimmed (chunks only) to {total_len} chars.")
        return trimmed

    # 3. Trim financial JSON dumps to keep only basic keys if still too large
    def condense_json_dump(match):
        label = match.group(1)
        json_str = match.group(2)
        try:
            obj = json.loads(json_str)
            condensed = {}
            if "Valuation" in label:
                if "wacc_details" in obj and isinstance(obj["wacc_details"], dict):
                    condensed["wacc"] = obj["wacc_details"].get("wacc")
                if "dcf_details" in obj and isinstance(obj["dcf_details"], dict):
                    condensed["intrinsic_price"] = obj["dcf_details"].get("intrinsic_share_price")
                    condensed["perpetuity_growth_rate"] = obj["dcf_details"].get("terminal_growth_rate")
                for key in ["confidence_score", "valuation_flags", "wacc_clamped_due_to_fallback_beta"]:
                    if key in obj:
                        condensed[key] = obj[key]
                
                # Format as plain text key-values
                parts = []
                if "wacc" in condensed and condensed["wacc"] is not None:
                    parts.append(f"WACC: {condensed['wacc'] * 100:.2f}%")
                if "intrinsic_price" in condensed and condensed["intrinsic_price"] is not None:
                    parts.append(f"Intrinsic Price: {condensed['intrinsic_price']}")
                if "perpetuity_growth_rate" in condensed and condensed["perpetuity_growth_rate"] is not None:
                    parts.append(f"Perpetuity Growth: {condensed['perpetuity_growth_rate'] * 100:.2f}%")
                if condensed.get("valuation_flags"):
                    parts.append(f"Valuation Flags: {', '.join(condensed['valuation_flags'])}")
                if condensed.get("wacc_clamped_due_to_fallback_beta"):
                    parts.append("WACC Clamped: True")
                
                return f"{label}: " + (", ".join(parts) if parts else "No valuation details available.")
            else:
                for key in ["revenue", "ebit", "net_income", "gross_margin", "ebitda", "fiscal_year", "period_type", "currency"]:
                    if key in obj:
                        condensed[key] = obj[key]
                    elif "latest_statement" in obj and isinstance(obj["latest_statement"], dict) and key in obj["latest_statement"]:
                        condensed[key] = obj["latest_statement"][key]
                
                parts = []
                currency = condensed.get("currency") or "INR"
                for k, name in [("revenue", "Revenue"), ("ebit", "EBIT"), ("ebitda", "EBITDA"), ("net_income", "Net Income"), ("gross_margin", "Gross Margin")]:
                    val = condensed.get(k)
                    if val is not None:
                        if k == "gross_margin":
                            parts.append(f"{name}: {val * 100:.2f}%" if val < 1.0 else f"{name}: {val}%")
                        else:
                            parts.append(f"{name}: {val} {currency}")
                if condensed.get("fiscal_year"):
                    parts.append(f"Fiscal Year: {condensed['fiscal_year']}")
                return f"{label}: " + (", ".join(parts) if parts else "No financial metrics available.")
        except Exception:
            return f"{label}: {json_str[:500]}... [trimmed]"

    user_content = re.sub(
        r'(Financial Metrics|Valuation/DCF Metrics):\s*(\{.*?)(?=\n|$)',
        condense_json_dump,
        user_content
    )

    total_len = len(system_content) + len(user_content)
    trimmed[1]["content"] = user_content
    logger.info(f"Ollama prompt trimmed (chunks + financials) to {total_len} chars.")
    return trimmed


async def _ollama_fallback_async(
    messages: List[Dict[str, str]],
    original_failure: Exception,
    caller_label: str,
) -> str:
    """Invokes Ollama /api/chat as async fallback. Raises if Ollama also fails."""
    from app.core.config import settings

    logger.warning(
        f"[{caller_label}] OpenRouter failed ({type(original_failure).__name__}: "
        f"{str(original_failure)[:120]}). "
        f"Falling back to local Ollama model={settings.OLLAMA_MODEL}."
    )

    # Trim prompt to fit within local Ollama context window
    trimmed_messages = _trim_prompt_for_ollama(messages)

    # Build Ollama message list: copy trimmed messages + append a final
    # reinforcement at the LAST position (most-attended by the model).
    ollama_messages = list(trimmed_messages)
    ollama_messages.append({
        "role": "user",
        "content": (
            "IMPORTANT: Respond with ONLY a valid JSON object matching the schema "
            "described above. No markdown fences, no prose, no explanation — "
            "just the raw JSON object."
        ),
    })

    # Estimate total token count (rough estimate: chars / 4)
    total_chars = sum(len(m.get("content", "")) for m in ollama_messages)
    estimated_tokens = total_chars // 4
    if estimated_tokens > 8192:
        logger.warning(
            f"[{caller_label}] Trimmed prompt still exceeds local Ollama context window limit of 8192 tokens "
            f"(estimated: {estimated_tokens} tokens, {total_chars} chars). Grounding safety net will monitor output."
        )
    else:
        logger.info(
            f"[{caller_label}] Prompt size within Ollama limit: estimated {estimated_tokens} tokens ({total_chars} chars)."
        )

    # Determine target URL: try configured base URL first, fall back to localhost
    url_options = [settings.OLLAMA_BASE_URL]
    if "localhost" not in settings.OLLAMA_BASE_URL and "127.0.0.1" not in settings.OLLAMA_BASE_URL:
        url_options.append("http://localhost:11434")

    content = None
    last_ollama_err = None

    for base in url_options:
        url = f"{base.rstrip('/')}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": ollama_messages,
            "stream": False,
            "format": "json",  # API-level enforcement: model can only emit valid JSON tokens
            "options": {
                "num_ctx": 8192
            }
        }
        logger.debug(
            f"[{caller_label}] Ollama fallback POST {url} model={settings.OLLAMA_MODEL} "
            f"format=json messages={len(ollama_messages)}"
        )
        try:
            # llama3:8b first-token latency can be 20-60s on cold start — use 240s timeout
            async with httpx.AsyncClient(timeout=240.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                break
        except Exception as exc:
            last_ollama_err = exc
            logger.warning(
                f"[{caller_label}] Failed connecting to Ollama at {url}: {exc}. Trying next target..."
            )

    if content is None:
        raise last_ollama_err or RuntimeError("Failed connecting to Ollama endpoints.")

    logger.info(
        f"[{caller_label}] Ollama fallback served request successfully "
        f"(model={settings.OLLAMA_MODEL}, response_length={len(content)}, format=json)."
    )
    return content


def _ollama_fallback_sync(
    messages: List[Dict[str, str]],
    original_failure: Exception,
    caller_label: str,
) -> str:
    """Synchronous version of _ollama_fallback_async for Celery / sync paths."""
    from app.core.config import settings

    logger.warning(
        f"[{caller_label}] OpenRouter(sync) failed ({type(original_failure).__name__}: "
        f"{str(original_failure)[:120]}). "
        f"Falling back to local Ollama model={settings.OLLAMA_MODEL}."
    )

    # Trim prompt to fit within local Ollama context window
    trimmed_messages = _trim_prompt_for_ollama(messages)

    # Same prompt reinforcement as async variant
    ollama_messages = list(trimmed_messages)
    ollama_messages.append({
        "role": "user",
        "content": (
            "IMPORTANT: Respond with ONLY a valid JSON object matching the schema "
            "described above. No markdown fences, no prose, no explanation — "
            "just the raw JSON object."
        ),
    })

    # Estimate total token count (rough estimate: chars / 4)
    total_chars = sum(len(m.get("content", "")) for m in ollama_messages)
    estimated_tokens = total_chars // 4
    if estimated_tokens > 8192:
        logger.warning(
            f"[{caller_label}] Trimmed prompt still exceeds local Ollama context window limit of 8192 tokens "
            f"(estimated: {estimated_tokens} tokens, {total_chars} chars). Grounding safety net will monitor output."
        )
    else:
        logger.info(
            f"[{caller_label}] Prompt size within Ollama limit: estimated {estimated_tokens} tokens ({total_chars} chars)."
        )

    url_options = [settings.OLLAMA_BASE_URL]
    if "localhost" not in settings.OLLAMA_BASE_URL and "127.0.0.1" not in settings.OLLAMA_BASE_URL:
        url_options.append("http://localhost:11434")

    content = None
    last_ollama_err = None

    for base in url_options:
        url = f"{base.rstrip('/')}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": ollama_messages,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": 8192
            }
        }
        logger.debug(
            f"[{caller_label}] Ollama fallback(sync) POST {url} model={settings.OLLAMA_MODEL} "
            f"format=json messages={len(ollama_messages)}"
        )
        try:
            with httpx.Client(timeout=240.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                break
        except Exception as exc:
            last_ollama_err = exc
            logger.warning(
                f"[{caller_label}] Failed connecting to Ollama(sync) at {url}: {exc}. Trying next target..."
            )

    if content is None:
        raise last_ollama_err or RuntimeError("Failed connecting to Ollama endpoints (sync).")

    logger.info(
        f"[{caller_label}] Ollama fallback(sync) served request successfully "
        f"(model={settings.OLLAMA_MODEL}, response_length={len(content)}, format=json)."
    )
    return content


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def openrouter_chat(
    messages: List[Dict[str, str]],
    model: str,
    api_key: str,
    base_url: str = _DEFAULT_BASE_URL,
    timeout: float = 120.0,
    max_retries: int = 1,
    caller_label: str = "OpenRouterClient",
    allow_ollama_fallback: bool = False,
) -> LLMResult:
    """
    Calls the OpenRouter /chat/completions endpoint.

    Returns ``LLMResult(content, provider_used)``.

    Fallback policy:
    - If allow_ollama_fallback is True:
        - 429 → skip remaining retries, immediately invoke Ollama fallback.
        - network/timeout exhaustion → invoke Ollama fallback.
    - If allow_ollama_fallback is False:
        - Raise the original exception on failure (OpenRouter only).
    - 401/403 → raise PermissionError immediately (no fallback regardless of flag).
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = _build_headers(api_key)
    payload = {"model": model, "messages": messages}

    logger.debug(
        f"[{caller_label}] OpenRouter POST {url} model={model} messages={len(messages)}"
    )

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 2.0 * attempt
            logger.warning(
                f"[{caller_label}] Retrying OpenRouter (attempt {attempt}/{max_retries}) "
                f"after {wait}s…"
            )
            await asyncio.sleep(wait)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)

            # Auth errors — fail immediately, never fall back to Ollama
            if resp.status_code in _AUTH_STATUS_CODES:
                raise PermissionError(
                    f"[{caller_label}] OpenRouter authentication failed "
                    f"(HTTP {resp.status_code}). Check OPENROUTER_API_KEY."
                )

            # Errors eligible for Ollama fallback when allow_ollama_fallback is True (404 model not found, 429 rate limit, 5xx server errors)
            if resp.status_code in {404, 429} or (500 <= resp.status_code < 600):
                body = resp.text[:200]
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}: {body}", request=resp.request, response=resp,
                )
                if allow_ollama_fallback:
                    logger.warning(
                        f"[{caller_label}] OpenRouter HTTP {resp.status_code}. "
                        "Skipping remaining retries — will fall back to Ollama."
                    )
                    break  # exit retry loop immediately to invoke Ollama
                else:
                    logger.warning(
                        f"[{caller_label}] OpenRouter HTTP {resp.status_code} "
                        f"(fallback disabled for this call site)."
                    )
                    if resp.status_code in _TRANSIENT_STATUS_CODES:
                        continue
                    else:
                        resp.raise_for_status()

            # Other transient server errors — retry up to max_retries
            if resp.status_code in _TRANSIENT_STATUS_CODES:
                body = resp.text[:200]
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}: {body}", request=resp.request, response=resp,
                )
                logger.warning(
                    f"[{caller_label}] OpenRouter transient HTTP {resp.status_code} "
                    f"(attempt {attempt + 1}/{max_retries + 1}). Body: {body}"
                )
                continue

            # Other non-2xx — raise immediately
            resp.raise_for_status()

            data = resp.json()
            try:
                content: str = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"[{caller_label}] Unexpected /chat/completions response shape: {data}"
                ) from exc

            logger.debug(
                f"[{caller_label}] OpenRouter success "
                f"(attempt={attempt + 1}, length={len(content)}, provider=openrouter)"
            )
            return LLMResult(content=content, provider_used="openrouter")

        except PermissionError:
            raise  # never retry or fall back on auth errors
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as net_exc:
            last_exc = net_exc
            logger.warning(
                f"[{caller_label}] OpenRouter network error on attempt "
                f"{attempt + 1}/{max_retries + 1}: {type(net_exc).__name__}: {net_exc}"
            )
            continue

    # --- All OpenRouter attempts exhausted ---
    if allow_ollama_fallback and last_exc is not None:
        try:
            content = await _ollama_fallback_async(messages, last_exc, caller_label)
            return LLMResult(content=content, provider_used="ollama_fallback")
        except Exception as ollama_exc:
            logger.error(
                f"[{caller_label}] Ollama fallback also failed: {ollama_exc}. "
                "Both OpenRouter and local Ollama are unavailable."
            )
            raise RuntimeError(
                f"[{caller_label}] OpenRouter failed ({last_exc}) and "
                f"Ollama fallback failed ({ollama_exc})."
            ) from last_exc

    if last_exc is not None:
        raise last_exc

    raise RuntimeError(
        f"[{caller_label}] All {max_retries + 1} attempts failed."
    )



# ---------------------------------------------------------------------------
# Public sync API (Celery workers / synchronous call sites)
# ---------------------------------------------------------------------------

def openrouter_chat_sync(
    messages: List[Dict[str, str]],
    model: str,
    api_key: str,
    base_url: str = _DEFAULT_BASE_URL,
    timeout: float = 120.0,
    max_retries: int = 1,
    caller_label: str = "OpenRouterClient(sync)",
    allow_ollama_fallback: bool = False,
) -> LLMResult:
    """
    Synchronous version of openrouter_chat() for use in Celery workers or
    other non-async call sites (e.g. financial intelligence parser).

    Same retry and fallback policy as the async variant.
    Returns ``LLMResult(content, provider_used)``.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = _build_headers(api_key)
    payload = {"model": model, "messages": messages}

    logger.debug(
        f"[{caller_label}] OpenRouter POST {url} model={model} messages={len(messages)}"
    )

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 2.0 * attempt
            logger.warning(
                f"[{caller_label}] Retrying OpenRouter (attempt {attempt}/{max_retries}) "
                f"after {wait}s…"
            )
            time.sleep(wait)

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload, headers=headers)

            if resp.status_code in _AUTH_STATUS_CODES:
                raise PermissionError(
                    f"[{caller_label}] OpenRouter authentication failed "
                    f"(HTTP {resp.status_code}). Check OPENROUTER_API_KEY."
                )

            if resp.status_code in {404, 429} or (500 <= resp.status_code < 600):
                body = resp.text[:200]
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}: {body}", request=resp.request, response=resp,
                )
                if allow_ollama_fallback:
                    logger.warning(
                        f"[{caller_label}] OpenRouter HTTP {resp.status_code}. "
                        "Skipping remaining retries — will fall back to Ollama."
                    )
                    break
                else:
                    logger.warning(
                        f"[{caller_label}] OpenRouter HTTP {resp.status_code} "
                        f"(fallback disabled for this call site)."
                    )
                    if resp.status_code in _TRANSIENT_STATUS_CODES:
                        continue
                    else:
                        resp.raise_for_status()

            if resp.status_code in _TRANSIENT_STATUS_CODES:
                body = resp.text[:200]
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}: {body}", request=resp.request, response=resp,
                )
                logger.warning(
                    f"[{caller_label}] OpenRouter transient HTTP {resp.status_code} "
                    f"(attempt {attempt + 1}/{max_retries + 1})."
                )
                continue

            resp.raise_for_status()

            data = resp.json()
            try:
                content: str = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"[{caller_label}] Unexpected response shape: {data}"
                ) from exc

            logger.debug(
                f"[{caller_label}] OpenRouter success "
                f"(attempt={attempt + 1}, length={len(content)}, provider=openrouter)"
            )
            return LLMResult(content=content, provider_used="openrouter")

        except PermissionError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as net_exc:
            last_exc = net_exc
            logger.warning(
                f"[{caller_label}] OpenRouter network error on attempt "
                f"{attempt + 1}/{max_retries + 1}: {type(net_exc).__name__}: {net_exc}"
            )
            continue

    # --- All OpenRouter attempts exhausted ---
    if allow_ollama_fallback and last_exc is not None:
        try:
            content = _ollama_fallback_sync(messages, last_exc, caller_label)
            return LLMResult(content=content, provider_used="ollama_fallback")
        except Exception as ollama_exc:
            logger.error(
                f"[{caller_label}] Ollama fallback(sync) also failed: {ollama_exc}. "
                "Both OpenRouter and local Ollama are unavailable."
            )
            raise RuntimeError(
                f"[{caller_label}] OpenRouter failed ({last_exc}) and "
                f"Ollama fallback failed ({ollama_exc})."
            ) from last_exc

    if last_exc is not None:
        raise last_exc

    raise RuntimeError(
        f"[{caller_label}] All {max_retries + 1} attempts failed."
    )


