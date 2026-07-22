from typing import List, Union
import httpx
from app.core.config import settings
from loguru import logger
from app.core.cache import cache
import time

OLLAMA_EMBED_BATCH_SIZE = 50


class EmbeddingService:
    """
    Service for generating vector embeddings using Ollama and the BGE-M3 model.

    Embeddings are produced via Ollama's /api/embed endpoint (HTTP REST).
    Requires: ollama pull bge-m3

    BGE-M3 outputs 1024-dimensional vectors. No special input prefixes
    (e.g. 'search_document:' / 'search_query:') are required — pass text as-is.
    """
    def __init__(self):
        self.provider = "ollama"
        self.model = settings.EMBEDDING_MODEL
        self.base_url = settings.OLLAMA_BASE_URL
        self.is_mock_mode = False

        logger.info(f"EmbeddingService initialized with provider={self.provider}, model={self.model} at {self.base_url}")

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates embedding for a single query string using Ollama's /api/embed.
        Utilizes Redis cache to save compute.
        """
        text_hash = cache.hash_key(text)
        cache_key = f"embedding:{self.model}:{text_hash}"

        cached = cache.get_sync(cache_key)
        if cached is not None:
            return cached

        logger.info(f"EmbeddingService: Generating query embedding via model={self.model} on {self.provider}...")
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": text
                    },
                    timeout=60.0
                )
                if response.status_code >= 400:
                    logger.error(f"EmbeddingService: Ollama rejected request ({response.status_code}): {response.text}")
                response.raise_for_status()
                res_data = response.json()
                emb = res_data["embeddings"][0]

            cache.set_sync(cache_key, emb, ttl=2592000)  # cache for 30 days
            return emb
        except Exception as e:
            logger.error(f"EmbeddingService: Failed to generate query embedding via Ollama: {e}")
            raise

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of document chunk strings using Ollama's /api/embed.
        Uses BGE-M3 (1024-dim). Utilizes Redis cache for individual chunk matches.
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

        # Pre-flight check: scan all input chunk_texts
        empty_chunk_indices = [i for i, t in enumerate(texts) if not t or not t.strip()]
        if empty_chunk_indices:
            logger.warning(f"EmbeddingService: Found {len(empty_chunk_indices)} empty, None, or whitespace-only chunks in chunk_texts at indices {empty_chunk_indices}")

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
                f"({len(batch_texts)} chunks, longest={sub_max_len} chars, "
                f"payload={sub_total_bytes} bytes) via model={self.model} on {self.provider}..."
            )

            embeddings = None
            for attempt in range(2):
                try:
                    with httpx.Client() as client:
                        response = client.post(
                            f"{self.base_url}/api/embed",
                            json={
                                "model": self.model,
                                "input": batch_texts,
                            },
                            timeout=60.0
                        )
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError as e:
                            logger.error(
                                f"EmbeddingService: Ollama rejected sub-batch request ({response.status_code}): {response.text}. "
                                f"Sub-batch size: {len(batch_texts)} chunks. "
                                f"Request payload size: {sub_total_bytes} bytes."
                            )
                            raise e

                        res_data = response.json()
                        embeddings = res_data["embeddings"]
                        break
                except Exception as attempt_err:
                    if attempt == 0:
                        logger.warning(
                            f"EmbeddingService: Sub-batch {batch_num} failed on first attempt: {attempt_err}. "
                            "Retrying in 2 seconds..."
                        )
                        time.sleep(2.0)
                    else:
                        logger.error(f"EmbeddingService: Sub-batch {batch_num} failed on all attempts: {attempt_err}")
                        raise attempt_err

            # Process, store in results, and cache individual results for this sub-batch
            for idx_in_sub, emb in enumerate(embeddings):
                orig_idx = batch_indices[idx_in_sub]
                results[orig_idx] = emb

                text_hash = cache.hash_key(batch_texts[idx_in_sub])
                cache_key = f"embedding:{self.model}:{text_hash}"
                cache.set_sync(cache_key, emb, ttl=2592000)

        return results
