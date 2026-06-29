# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Embedding service using DashScope via OpenAI compatible protocol.

V3.7 P0.1 Performance optimizations:
- TTL-based memory cache for query embeddings (5-minute TTL)
- Module-level singleton httpx.Client connection pool (eliminates TLS handshake per request)
- EmbeddingService reuses global client instead of creating per-instance
"""

import time
import logging
import threading
import httpx
from django.conf import settings

from .config import EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Thread-safe TTL cache for embedding results.

    Caches query → embedding vectors with a configurable TTL.
    When the same query is requested within the TTL window, the cached
    result is returned immediately — eliminating the ~1,000-1,500ms
    DashScope API call latency.

    Cache stats are logged periodically for monitoring.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        self._cache: dict[str, tuple[list[float], float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> list[float] | None:
        """Retrieve cached embedding if still within TTL."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            embedding, timestamp = entry
            if time.time() - timestamp > self._ttl:
                # TTL expired — evict
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return embedding
        # V3.7: Log hit rate outside the lock to avoid I/O blocking other threads

    def log_stats(self) -> None:
        """Log cache statistics (call outside the lock)."""
        with self._lock:
            total = self._hits + self._misses
            if total > 0 and total % 50 == 0:
                hit_rate = self._hits / total * 100
                logger.info(
                    "[EmbeddingCache] hits=%d misses=%d hit_rate=%.1f%% size=%d",
                    self._hits, self._misses, hit_rate, len(self._cache),
                )

    def set(self, key: str, embedding: list[float]) -> None:
        """Store embedding result with current timestamp."""
        with self._lock:
            # Evict oldest entries if cache exceeds max size
            if len(self._cache) >= self._max_size:
                # Remove expired entries first
                now = time.time()
                expired_keys = [
                    k for k, (_, ts) in self._cache.items()
                    if now - ts > self._ttl
                ]
                for k in expired_keys:
                    del self._cache[k]
                # If still over limit, evict oldest entries
                if len(self._cache) >= self._max_size:
                    sorted_keys = sorted(
                        self._cache.keys(),
                        key=lambda k: self._cache[k][1],
                    )
                    for k in sorted_keys[:len(self._cache) - self._max_size + 1]:
                        del self._cache[k]
            self._cache[key] = (embedding, time.time())

    def clear(self) -> None:
        """Clear entire cache (e.g., for testing)."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / max(1, self._hits + self._misses) * 100,
            }


# Global singleton resources — shared across ALL EmbeddingService instances
# This is the key fix: httpx.Client is created ONCE and reused across ALL
# /send/ requests, eliminating ~100-200ms TLS handshake per request.
_embedding_cache = EmbeddingCache(ttl_seconds=300, max_size=1000)

# Global httpx.Client with connection pool limits — shared by EmbeddingService
# and LiteLLMChatService. Created once at module load, never recreated per request.
_global_httpx_client: httpx.Client | None = None
_client_lock = threading.Lock()


def get_shared_httpx_client() -> httpx.Client:
    """Get or create the global shared httpx.Client.

    Thread-safe singleton — all EmbeddingService and LiteLLMChatService
    instances share this connection pool, eliminating TLS handshake
    overhead for repeated requests to the same DashScope API endpoint.
    """
    global _global_httpx_client
    if _global_httpx_client is not None:
        return _global_httpx_client
    with _client_lock:
        if _global_httpx_client is None:
            _global_httpx_client = httpx.Client(
                verify=settings.SSL_VERIFY,
                timeout=120,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=60,
                ),
            )
            logger.info("[V3.7 P0.1] Shared httpx.Client created — connection pool ready")
        return _global_httpx_client


def recreate_shared_httpx_client() -> httpx.Client:
    """Recreate the global shared httpx.Client after a connection error.

    Thread-safe — closes old client and creates new one under lock.
    """
    global _global_httpx_client
    with _client_lock:
        old_client = _global_httpx_client
        _global_httpx_client = httpx.Client(
            verify=settings.SSL_VERIFY,
            timeout=120,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=60,
            ),
        )
        logger.info("[V3.7 P0.1] Shared httpx.Client recreated — connection pool reset")
    # Close old client outside the lock to avoid blocking
    if old_client is not None:
        try:
            old_client.close()
        except Exception:
            pass
    return _global_httpx_client


class EmbeddingService:
    """Handles text embedding generation via DashScope API.

    V3.7 optimizations:
    - Uses global shared httpx.Client (get_shared_httpx_client) — no per-instance
      client creation, eliminating ~100-200ms TLS handshake overhead per request.
    - TTL cache for single-text embed() calls eliminates redundant API calls.
    """

    def __init__(self, model=None):
        self.model = model or EMBEDDING_MODEL
        self.api_key = settings.DASHSCOPE_API_KEY
        self.base_url = settings.LITELLM_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # V3.7 P0.1+P1.1: Reuse global shared httpx.Client — no per-instance connection pool
        self._client = get_shared_httpx_client()
        self._cache = _embedding_cache

    def _make_request(self, input_texts: list[str], retries: int = 3) -> dict:
        """Make embedding API request with retry logic.

        V3.7: Uses global shared httpx.Client — no TLS handshake per request.
        """
        payload = {
            "model": self.model,
            "input": input_texts,
        }

        for attempt in range(retries):
            try:
                # V3.7: Reuse global shared connection — no TLS handshake per request
                response = self._client.post(
                    f"{self.base_url}/embeddings",
                    headers=self.headers,
                    json=payload,
                )
                if response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Embedding API error: {e.response.status_code} - {e.response.text[:200]}")
                raise
            except httpx.ConnectError as e:
                # Connection error — recreate global shared client and retry
                logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                recreate_shared_httpx_client()
                self._client = get_shared_httpx_client()
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        V3.7: Uses TTL cache — if the same text was embedded within
        the last 5 minutes, returns cached result immediately
        (eliminating ~1,000-1,500ms DashScope API latency).
        """
        # Truncate very long texts to avoid API errors
        if len(text) > 8000:
            text = text[:8000]

        # V3.7 P0.1: Check cache first
        cached = self._cache.get(text)
        self._cache.log_stats()  # Outside lock — see EmbeddingCache.log_stats()
        if cached is not None:
            logger.debug("[EmbeddingService] Cache hit for query: '%s...' (len=%d)", text[:50], len(text))
            return cached

        # Cache miss — call API
        result = self._make_request([text])
        embedding = result["data"][0]["embedding"]

        # Store in cache for future requests
        self._cache.set(text, embedding)
        logger.debug("[EmbeddingService] Cache miss — API call completed for query: '%s...'", text[:50])

        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Process one at a time for reliability with DashScope API.
        V3.7: Each text is also cached individually.
        """
        embeddings = []
        for i, text in enumerate(texts):
            # Truncate very long texts
            if len(text) > 8000:
                text = text[:8000]
            try:
                # V3.7: Check cache for each text in batch
                cached = self._cache.get(text)
                if cached is not None:
                    embeddings.append(cached)
                    continue

                result = self._make_request([text])
                embedding = result["data"][0]["embedding"]
                self._cache.set(text, embedding)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to embed chunk {i}: {e}")
                # Use zero vector as fallback
                embeddings.append([0.0] * EMBEDDING_DIM)
            # Rate limiting: small delay between requests
            if i % 5 == 4:
                time.sleep(0.5)
        return embeddings
