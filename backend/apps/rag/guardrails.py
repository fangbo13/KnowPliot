"""Prompt injection detection and output filtering."""

import json
import re
import httpx

from django.conf import settings


class GuardrailsService:
    """Prompt injection detection and output filtering."""

    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(previous|all)\s+(instructions|rules)",
        r"(?i)system\s*:\s*",
        r"(?i)<\|im_start\|>",
        r"(?i)dan\s+mode",
        r"(?i)jailbreak",
        r"(?i)you are now",
        r"(?i)forget\s+(all|everything|your)\s+(previous|prior)",
        r"(?i)disregard\s+(all|the)\s+(previous|prior|above)",
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

        llm = LiteLLMChatService()
        yield from llm.stream_chat(system_prompt, user_query)


class LiteLLMChatService:
    """LLM chat service via DashScope OpenAI-compatible API."""

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.base_url = settings.LITELLM_BASE_URL
        self.model = settings.RAG_LLM_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def stream_chat(self, system_prompt, user_query):
        """Stream chat response from LLM via SSE."""
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

        with httpx.Client(verify=False, timeout=120) as client:
            with client.stream(
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
