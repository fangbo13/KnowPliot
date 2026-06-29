# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Prompt injection detection and output filtering.

V3.7 P1.1: LiteLLMChatService now uses the global shared httpx.Client
(get_shared_httpx_client from embedding.py) for connection pool reuse,
eliminating per-request TLS handshake overhead. The client is shared
with EmbeddingService for maximum connection reuse efficiency.
"""

import json
import re
import logging
import httpx

from django.conf import settings
from .embedding import get_shared_httpx_client, recreate_shared_httpx_client

logger = logging.getLogger(__name__)


class GuardrailsService:
    """Prompt injection detection and output filtering."""

    INJECTION_PATTERNS = [
        # Broadened: "ignore" ... "instructions/rules/directives" with arbitrary words between
        r"(?i)ignore\b.*?\b(instructions?|rules?|directives?|guidelines?|constraints?)",
        # Broadened: "forget/disregard" ... "previous/prior"
        r"(?i)(?:forget|disregard)\b.*?\b(previous|prior|above|earlier)",
        # System prompt injection — match "system:" only at start of line to avoid false positives
        # on legitimate questions like "How do I set up my system email?"
        r"(?im)^system\s*:",
        r"(?i)<\|im_start\|>",
        r"(?i)<\|im_end\|>",
        # Role-playing attacks
        r"(?i)dan\s+mode",
        r"(?i)jailbreak",
        r"(?i)you are now",
        r"(?i)act as (a |an )",
        r"(?i)pretend (to |you |that )",
        # Developer/override claims
        r"(?i)(?:new (instructions?|rules?|directives?)\s*:)",
        r"(?i)(?:override|bypass|disable)\b.*?\b(safety|security|rules?|constraints?|guardrails?|filters?)",
        # Instruction terminator patterns
        r"(?i)(?:end of (instructions?|system|prompt))",
        r"(?i)(?:---\s*(?:new|user|admin|developer)\s+(?:instructions?|command|prompt))",
        # Hypothetical framing
        r"(?i)(?:hypothetically|in a hypothetical|imagine|suppose)\b.*?\b(ignore|bypass|override|no longer)",
    ]

    def check_input(self, query: str) -> bool:
        """Return False if input looks like prompt injection."""
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, query):
                return False
        return True

    def generate_fallback(self, language="en"):
        """Generate a safe fallback response."""
        if language == "zh":
            return "抱歉，我无法处理该请求。"
        return "I'm sorry, I cannot process that request."

    def call_with_safety(self, system_prompt, user_query, stream=True, language="en"):
        """Check input for injection, then call LLM if safe."""
        if not self.check_input(user_query):
            yield self.generate_fallback(language)
            return

        # V3.7 P1.1: Use module-level singleton (reuses global httpx.Client)
        llm = LiteLLMChatService()
        yield from llm.stream_chat(system_prompt, user_query)


# V3.7 P1.1: Module-level singleton — reuses the same httpx.Client as EmbeddingService
# This means the LLM streaming connection also benefits from TLS session resumption
# and TCP keep-alive, saving ~100-200ms per /send/ request.
_llm_service = None


def get_llm_service() -> "LiteLLMChatService":
    """Get or create the global LiteLLMChatService singleton.

    Uses the same shared httpx.Client as EmbeddingService for
    maximum connection reuse efficiency.
    """
    global _llm_service
    if _llm_service is None:
        _llm_service = LiteLLMChatService()
        logger.info("[V3.7 P1.1] LiteLLMChatService singleton created — sharing global httpx.Client")
    return _llm_service


class LiteLLMChatService:
    """LLM chat service via DashScope OpenAI-compatible API.

    V3.7 P1.1: Uses global shared httpx.Client (from embedding.py)
    for connection pool reuse — eliminates ~100-200ms TLS handshake
    per streaming request. Client is shared with EmbeddingService.
    """

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.base_url = settings.LITELLM_BASE_URL
        self.model = settings.RAG_LLM_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # V3.7 P1.1: Reuse global shared httpx.Client — shared with EmbeddingService
        self._client = get_shared_httpx_client()

    def stream_chat(self, system_prompt, user_query):
        """Stream chat response from LLM via SSE.

        V3.7: Uses global shared httpx.Client — no TLS handshake per request.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            "stream": True,
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        try:
            # V3.7: Reuse global shared connection — no TLS handshake per request
            with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = (
                                data.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass
        except httpx.ConnectError as e:
            # Connection error — recreate global shared client
            logger.warning(f"Stream connection error: {e}")
            recreate_shared_httpx_client()
            self._client = get_shared_httpx_client()
            raise
