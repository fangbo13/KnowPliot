"""Embedding service using DashScope via OpenAI compatible protocol."""

import time
import logging
import httpx
from django.conf import settings

from .config import EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Handles text embedding generation via DashScope API."""

    def __init__(self, model=None):
        self.model = model or EMBEDDING_MODEL
        self.api_key = settings.DASHSCOPE_API_KEY
        self.base_url = settings.LITELLM_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _make_request(self, input_texts: list[str], retries: int = 3) -> dict:
        """Make embedding API request with retry logic."""
        payload = {
            "model": self.model,
            "input": input_texts,
        }

        for attempt in range(retries):
            try:
                with httpx.Client(verify=False, timeout=120) as client:
                    response = client.post(
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

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        # Truncate very long texts to avoid API errors
        if len(text) > 8000:
            text = text[:8000]
        result = self._make_request([text])
        return result["data"][0]["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Process one at a time for reliability with DashScope API.
        """
        embeddings = []
        for i, text in enumerate(texts):
            # Truncate very long texts
            if len(text) > 8000:
                text = text[:8000]
            try:
                result = self._make_request([text])
                embeddings.append(result["data"][0]["embedding"])
            except Exception as e:
                logger.error(f"Failed to embed chunk {i}: {e}")
                # Use zero vector as fallback
                embeddings.append([0.0] * EMBEDDING_DIM)
            # Rate limiting: small delay between requests
            if i % 5 == 4:
                time.sleep(0.5)
        return embeddings
