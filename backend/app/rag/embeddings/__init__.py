import time
from typing import List, Optional
import httpx
from loguru import logger
from redis.exceptions import LockError
from app.core.config import settings
from app.core.cache import cache

OLLAMA_EMBED_BATCH_SIZE = 50
OLLAMA_SHARED_LOCK_KEY = "lock:ollama:api"
OLLAMA_RETRIEVAL_SIGNAL_KEY = "signal:retrieval_pending"


class EmbeddingGenerationError(Exception):
    """Custom exception raised when vector embedding generation fails."""
    def __init__(self, message: str, batch_index: Optional[int] = None, chunk_count: Optional[int] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.batch_index = batch_index
        self.chunk_count = chunk_count
        self.cause = cause


class EmbeddingService:
    """
    Service layer for generating vector embeddings using Ollama (BGE-M3 1024-dim model).
    Includes Redis caching for single query embeddings and batch text chunks.
    Uses a single shared Redis lock 'lock:ollama:api' with priority signals for live user search.
    """
    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER if hasattr(settings, "EMBEDDING_PROVIDER") else "ollama"
        self.model = settings.EMBEDDING_MODEL
        self.base_url = settings.OLLAMA_BASE_URL
        self.is_mock_mode = False

    @property
    def embedding_model(self) -> str:
        return self.model

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates single query embedding for RAG vector retrieval with HIGH PRIORITY.
        Acquires the shared lock 'lock:ollama:api' with a 10s acquire timeout.
        """
        if not text:
            return []

        text_hash = cache.hash_key(text)
        cache_key = f"embedding:{self.model}:{text_hash}"

        cached_emb = cache.get_sync(cache_key)
        if cached_emb is not None:
            return cached_emb

        logger.info(f"EmbeddingService: Generating query embedding via model={self.model} on {self.provider}...")

        # 1. Signal background ingestion tasks that a live retrieval query is waiting
        try:
            cache.sync_client.set(OLLAMA_RETRIEVAL_SIGNAL_KEY, "1", ex=5)
        except Exception as cache_err:
            logger.warning(f"Failed to set retrieval priority signal in Redis: {cache_err}")

        urls = [self.base_url] if ("localhost" in self.base_url or "127.0.0.1" in self.base_url) else ["http://localhost:11434", self.base_url]

        # 2. Acquire the SHARED lock key with 10s timeout
        lock = cache.sync_client.lock(OLLAMA_SHARED_LOCK_KEY, timeout=30.0)
        acquired = False
        last_err = None
        try:
            acquired = lock.acquire(blocking_timeout=10.0)
            if not acquired:
                logger.error("Retrieval lock acquisition timed out after 10s. Ollama API busy.")
                raise RuntimeError("Search service currently busy under heavy load. Please try again.")

            for base in urls:
                try:
                    with httpx.Client(timeout=10.0) as client:
                        response = client.post(
                            f"{base.rstrip('/')}/api/embed",
                            json={"model": self.model, "input": text},
                        )
                        if response.status_code >= 400:
                            logger.error(f"EmbeddingService: Ollama rejected request ({response.status_code}): {response.text}")
                        response.raise_for_status()
                        res_data = response.json()
                        emb = res_data["embeddings"][0]

                        cache.set_sync(cache_key, emb, ttl=2592000)
                        return emb
                except Exception as e:
                    last_err = e
        finally:
            if acquired:
                try:
                    lock.release()
                except LockError:
                    pass
            try:
                cache.sync_client.delete(OLLAMA_RETRIEVAL_SIGNAL_KEY)
            except Exception:
                pass

        logger.error(f"EmbeddingService: Failed to generate query embedding via Ollama: {last_err}")
        if last_err is not None:
            raise last_err
        raise EmbeddingGenerationError("Failed to generate query embedding via Ollama", cause=last_err)

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of document chunk strings using Ollama's /api/embed.
        Acquires the shared lock 'lock:ollama:api' per sub-batch (50 chunks) with a 300ms yield window.
        """
        if not texts:
            return []

        results = [None] * len(texts)
        missing_indices = []
        missing_texts = []

        # Check cache for existing embeddings
        for idx, text in enumerate(texts):
            text_hash = cache.hash_key(text)
            cache_key = f"embedding:{self.model}:{text_hash}"
            cached_emb = cache.get_sync(cache_key)
            if cached_emb is not None:
                results[idx] = cached_emb
            else:
                missing_indices.append(idx)
                missing_texts.append(text)

        if not missing_texts:
            return results

        # Slicing input missing_texts into sub-batches of size OLLAMA_EMBED_BATCH_SIZE
        sub_batches = []
        for i in range(0, len(missing_texts), OLLAMA_EMBED_BATCH_SIZE):
            sub_batch_texts = missing_texts[i:i + OLLAMA_EMBED_BATCH_SIZE]
            sub_batch_indices = missing_indices[i:i + OLLAMA_EMBED_BATCH_SIZE]
            sub_batches.append((sub_batch_texts, sub_batch_indices))

        logger.info(
            f"EmbeddingService: Sliced {len(missing_texts)} missing chunks into "
            f"{len(sub_batches)} sub-batches (size={OLLAMA_EMBED_BATCH_SIZE}) for generation."
        )

        for batch_num, (batch_texts, batch_indices) in enumerate(sub_batches, 1):
            sub_max_len = max((len(t) for t in batch_texts), default=0)
            sub_total_bytes = sum(len(t.encode('utf-8')) for t in batch_texts)
            logger.info(
                f"EmbeddingService: Processing sub-batch {batch_num}/{len(sub_batches)} "
                f"({len(batch_texts)} chunks, longest={sub_max_len} chars, payload={sub_total_bytes} bytes)..."
            )

            # 1. Yield check: if retrieval is waiting, pause 500ms before attempting batch acquire
            try:
                if cache.sync_client.exists(OLLAMA_RETRIEVAL_SIGNAL_KEY):
                    logger.info("Live user retrieval query waiting. Ingestion pausing 500ms to yield lock...")
                    time.sleep(0.5)
            except Exception:
                pass

            # 2. Acquire the SHARED lock key for this single sub-batch
            lock = cache.sync_client.lock(OLLAMA_SHARED_LOCK_KEY, timeout=180.0)
            acquired = False
            embeddings = None
            last_err = None
            try:
                acquired = lock.acquire(blocking_timeout=60.0)
                if not acquired:
                    raise RuntimeError(f"Ingestion failed to acquire Ollama lock for batch {batch_num}")

                urls = [self.base_url] if ("localhost" in self.base_url or "127.0.0.1" in self.base_url) else ["http://localhost:11434", self.base_url]

                for base in urls:
                    try:
                        with httpx.Client(timeout=120.0) as client:
                            response = client.post(
                                f"{base.rstrip('/')}/api/embed",
                                json={
                                    "model": self.model,
                                    "input": batch_texts,
                                },
                            )
                            response.raise_for_status()
                            res_data = response.json()
                            embeddings = res_data["embeddings"]
                            break
                    except Exception as e:
                        last_err = e
                        logger.warning(f"EmbeddingService: Ollama request to {base} failed: {e}")
            finally:
                if acquired:
                    try:
                        lock.release()
                    except LockError:
                        pass

            if not embeddings:
                err_msg = (
                    f"EmbeddingService: Failed to generate embeddings for sub-batch {batch_num}/{len(sub_batches)} "
                    f"({len(batch_texts)} chunks) across all endpoints. Last error: {last_err}"
                )
                logger.error(err_msg)
                raise EmbeddingGenerationError(
                    err_msg, batch_index=batch_num, chunk_count=len(batch_texts), cause=last_err
                )

            # Process, store in results, and cache individual results for this sub-batch
            for idx_in_sub, emb in enumerate(embeddings):
                orig_idx = batch_indices[idx_in_sub]
                results[orig_idx] = emb

                text_hash = cache.hash_key(batch_texts[idx_in_sub])
                cache_key = f"embedding:{self.model}:{text_hash}"
                cache.set_sync(cache_key, emb, ttl=2592000)

            # 3. Mandatory 300ms yield window between sub-batches for live retrieval queries
            time.sleep(0.3)

        # Final assertion: ensure no None values exist in return array
        missing_count = sum(1 for r in results if r is None)
        if missing_count > 0:
            raise EmbeddingGenerationError(
                f"EmbeddingService: Incomplete generation result. {missing_count}/{len(texts)} embeddings failed.",
                chunk_count=missing_count,
            )

        return results
