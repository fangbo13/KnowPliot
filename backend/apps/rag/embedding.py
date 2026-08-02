# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Embedding service using DashScope via OpenAI compatible protocol.

V3.7 P0.1 Performance optimizations:
- TTL-based memory cache for query embeddings (5-minute TTL)
- Module-level singleton httpx.Client connection pool (eliminates TLS handshake per request)
- EmbeddingService reuses global client instead of creating per-instance

KB/RAG audit spec P1:
- §A5 embed_batch sends true batched API requests (was one call per text)
- §A8 query embeddings are shared across workers via the Django cache (Redis
  in production) as an L2 behind the in-process TTL cache
"""

import hashlib
import time
import logging
import threading
import httpx
from django.conf import settings
from django.core.cache import cache as shared_cache

from .config import EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)

# P1 §A5: DashScope OpenAI-compatible embeddings accept small input arrays.
EMBED_BATCH_SIZE = 10
# P1 §A8: cross-worker cache TTL (seconds).
SHARED_CACHE_TTL = 1800


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
                    max_connections=settings.PROVIDER_HTTP_MAX_CONNECTIONS,
                    max_keepalive_connections=(
                        settings.PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS
                    ),
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
                max_connections=settings.PROVIDER_HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=(
                    settings.PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS
                ),
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

    def _shared_cache_key(self, text: str) -> str:
        digest = hashlib.sha256(f"{self.model}:{text}".encode("utf-8")).hexdigest()
        return f"rag:embed:{digest}"

    def _shared_cache_get(self, text: str) -> list[float] | None:
        """P1 §A8: L2 lookup in the Django cache (Redis in production)."""
        try:
            value = shared_cache.get(self._shared_cache_key(text))
        except Exception:  # cache backend down — never block embedding
            return None
        return value if isinstance(value, list) and value else None

    def _shared_cache_set(self, text: str, embedding: list[float]) -> None:
        try:
            shared_cache.set(
                self._shared_cache_key(text), embedding, timeout=SHARED_CACHE_TTL
            )
        except Exception:
            pass

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        V3.7: in-process TTL cache (L1). P1 §A8: Django/Redis shared cache
        (L2) so cache hits survive across gunicorn workers and processes.
        """
        # Truncate very long texts to avoid API errors
        if len(text) > 8000:
            text = text[:8000]

        # V3.7 P0.1: Check L1 cache first
        cached = self._cache.get(text)
        self._cache.log_stats()  # Outside lock — see EmbeddingCache.log_stats()
        if cached is not None:
            logger.debug("[EmbeddingService] Cache hit for query: '%s...' (len=%d)", text[:50], len(text))
            return cached

        # P1 §A8: L2 shared cache (cross-worker)
        shared = self._shared_cache_get(text)
        if shared is not None:
            self._cache.set(text, shared)
            logger.debug("[EmbeddingService] Shared-cache hit for query: '%s...'", text[:50])
            return shared

        # Cache miss — call API
        result = self._make_request([text])
        embedding = result["data"][0]["embedding"]

        # Store in both cache layers for future requests
        self._cache.set(text, embedding)
        self._shared_cache_set(text, embedding)
        logger.debug("[EmbeddingService] Cache miss — API call completed for query: '%s...'", text[:50])

        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        P1 §A5: send true batched requests (EMBED_BATCH_SIZE inputs per API
        call) instead of one call per text — a 500-chunk document now needs
        ~50 requests with no fixed sleeps. A failed batch degrades to
        per-item requests; items that still fail fall back to zero vectors
        (detected downstream by BATCH-012).
        """
        truncated = [t[:8000] if len(t) > 8000 else t for t in texts]
        embeddings: list[list[float] | None] = [None] * len(truncated)

        pending: list[tuple[int, str]] = []
        for i, text in enumerate(truncated):
            cached = self._cache.get(text)
            if cached is not None:
                embeddings[i] = cached
            else:
                pending.append((i, text))

        for start in range(0, len(pending), EMBED_BATCH_SIZE):
            window = pending[start : start + EMBED_BATCH_SIZE]
            batch_texts = [text for _, text in window]
            try:
                result = self._make_request(batch_texts)
                data = sorted(result["data"], key=lambda item: item.get("index", 0))
                if len(data) != len(window):
                    raise ValueError(
                        f"embedding batch size mismatch: sent {len(window)}, got {len(data)}"
                    )
                for (i, text), item in zip(window, data):
                    embedding = item["embedding"]
                    self._cache.set(text, embedding)
                    embeddings[i] = embedding
            except Exception as exc:
                logger.warning(
                    "Batch embedding failed (%d items) — degrading to per-item calls: %s",
                    len(window), exc,
                )
                for i, text in window:
                    try:
                        result = self._make_request([text])
                        embedding = result["data"][0]["embedding"]
                        self._cache.set(text, embedding)
                        embeddings[i] = embedding
                    except Exception as item_exc:
                        logger.error(f"Failed to embed chunk {i}: {item_exc}")
                        embeddings[i] = [0.0] * EMBEDDING_DIM

        return [e if e is not None else [0.0] * EMBEDDING_DIM for e in embeddings]
