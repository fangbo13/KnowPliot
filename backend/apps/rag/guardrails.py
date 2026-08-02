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
import logging
import re
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import httpx
from django.conf import settings

from .embedding import get_shared_httpx_client

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
        # RAG optimization spec Phase 8: Chinese injection patterns. The English
        # rules above never matched Chinese, so "请忽略之前的指令" passed straight
        # through. Patterns target imperative-verb + object shapes rather than
        # single words to keep benign questions (e.g. "公司规则忽略节假日吗")
        # from tripping the filter.
        # 忽略/无视/忽视/忘记/抛开 … (之前|以上|上面|先前|所有|前面) … 指令/规则/设定/提示/限制
        r"(?:忽略|无视|忽视|忘记|抛开|不要管)[^。\n]{0,12}(?:之前|以上|上面|先前|所有|前面|既定)?[^。\n]{0,6}(?:指令|命令|规则|规定|设定|提示词?|限制|约束)",
        # 你现在是 / 你不再是 / 从现在开始你 (角色接管)
        r"你现在是(?!否|不是)",
        r"你不再是",
        r"从现在开始，?你",
        # 扮演/假装 (你是|自己是|成为) — role-play
        r"(?:扮演|假装|模拟你是)[^。\n]{0,8}(?:你是|自己是|一个|黑客|管理员|成为)",
        # 越狱 / 开发者模式 / DAN
        r"越狱",
        r"开发者模式",
        # 绕过/突破/禁用/关闭 … (安全|限制|规则|过滤|护栏|防护)
        r"(?:绕过|突破|禁用|关闭|解除)[^。\n]{0,8}(?:安全|限制|规则|过滤|护栏|防护|审查)",
        # 索取/泄露系统提示词 — prompt-leak probing (动词在提示词前后均可)
        r"(?:告诉我|输出|打印|发给我|显示|泄露|给我)[^。\n]{0,10}(?:系统)?提示词",
        r"(?:系统)?提示词[^。\n]{0,10}(?:原文)?(?:发|告诉|给|输出|打印|显示|泄露)",
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
        llm = get_llm_service()
        yield from llm.stream_chat(system_prompt, user_query)


# V3.7 P1.1: Module-level singleton — reuses the same httpx.Client as EmbeddingService
# This means the LLM streaming connection also benefits from TLS session resumption
# and TCP keep-alive, saving ~100-200ms per /send/ request.
_llm_service = None
_llm_service_lock = threading.Lock()


def get_llm_service() -> "LiteLLMChatService":
    """Get or create the global LiteLLMChatService singleton.

    Uses the same shared httpx.Client as EmbeddingService for
    maximum connection reuse efficiency.
    """
    global _llm_service
    if _llm_service is None:
        with _llm_service_lock:
            if _llm_service is None:
                _llm_service = LiteLLMChatService()
        logger.info("[V3.7 P1.1] LiteLLMChatService singleton created — sharing global httpx.Client")
    return _llm_service


@dataclass(frozen=True)
class ProviderStreamPart:
    """Typed provider output that cannot carry provider reasoning text."""

    kind: str
    text: str = ""
    duration_ms: int | None = None


def parse_provider_stream(
    lines: Iterable[str | bytes],
    *,
    clock=time.monotonic,
) -> Iterator[ProviderStreamPart]:
    """Discard reasoning text while retaining numeric reasoning duration."""

    reasoning_started_at = None
    for raw_line in lines:
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", errors="ignore")
        if not raw_line.startswith("data: "):
            continue
        data_str = raw_line[6:]
        if data_str == "[DONE]":
            break
        try:
            data = json.loads(data_str)
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta", {})
            if not isinstance(delta, dict):
                continue
        except (json.JSONDecodeError, AttributeError, IndexError, TypeError):
            continue

        if delta.get("reasoning_content") and reasoning_started_at is None:
            reasoning_started_at = clock()
        content = delta.get("content")
        if isinstance(content, str) and content:
            if reasoning_started_at is not None:
                yield ProviderStreamPart(
                    kind="reasoning_duration",
                    duration_ms=max(
                        0, int(round((clock() - reasoning_started_at) * 1000))
                    ),
                )
                reasoning_started_at = None
            yield ProviderStreamPart(kind="answer_delta", text=str(content))

    if reasoning_started_at is not None:
        yield ProviderStreamPart(
            kind="reasoning_duration",
            duration_ms=max(0, int(round((clock() - reasoning_started_at) * 1000))),
        )


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

    def _build_messages(self, system_prompt, user_query, history_messages=None):
        """Compose the messages array; recent history rides as real turns.

        Only user/assistant roles are accepted from history — anything else
        is coerced to user so callers can never smuggle a second system role.
        """
        messages = [{"role": "system", "content": system_prompt}]
        for item in history_messages or []:
            role = item.get("role")
            content = item.get("content", "")
            if not isinstance(content, str) or not content:
                continue
            if role not in ("user", "assistant"):
                role = "user"
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_query})
        return messages

    def stream_chat_parts(
        self,
        system_prompt,
        user_query,
        *,
        model_id=None,
        thinking_enabled=False,
        thinking_budget=None,
        history_messages=None,
    ):
        """Stream chat response from LLM via SSE.

        V3.7: Uses global shared httpx.Client — no TLS handshake per request.
        Session memory: ``history_messages`` carries the recent multi-turn
        window as standard messages instead of flattened system-prompt text.
        """
        payload = {
            "model": model_id or self.model,
            "messages": self._build_messages(
                system_prompt, user_query, history_messages
            ),
            "stream": True,
            "temperature": 0.3,
            "max_tokens": settings.PROVIDER_MAX_OUTPUT_TOKENS,
            "enable_thinking": bool(thinking_enabled),
        }
        if thinking_enabled and thinking_budget is not None:
            payload["thinking_budget"] = int(thinking_budget)

        try:
            # V3.7: Reuse global shared connection — no TLS handshake per request
            with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                yield from parse_provider_stream(response.iter_lines())
        except httpx.ConnectError:
            # A shared client stays live for concurrent streams; the pool can recover.
            logger.warning("provider_stream_connection_error code=connection_error")
            raise

    def stream_chat(
        self,
        system_prompt,
        user_query,
        *,
        model_id=None,
        thinking_enabled=False,
        thinking_budget=None,
    ):
        """Compatibility answer-only stream; provider reasoning never escapes."""

        for part in self.stream_chat_parts(
            system_prompt,
            user_query,
            model_id=model_id,
            thinking_enabled=thinking_enabled,
            thinking_budget=thinking_budget,
        ):
            if part.kind == "answer_delta":
                yield part.text

    def complete(
        self,
        system_prompt,
        user_prompt,
        *,
        model_id=None,
        max_tokens=512,
        temperature=0.0,
        timeout=None,
    ):
        """One non-streaming completion (session summary / query rewrite).

        Reuses the shared httpx.Client; ``timeout`` overrides the client
        default per request so latency-sensitive callers can fail fast.
        """
        payload = {
            "model": model_id or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": temperature,
            "max_tokens": int(max_tokens),
            # Non-streaming Qwen calls require thinking disabled.
            "enable_thinking": False,
        }
        kwargs = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self._client.post(
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json=payload,
            **kwargs,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        return content if isinstance(content, str) else ""
