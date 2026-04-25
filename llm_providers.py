"""LLM provider abstraction — pluggable backends for match scoring.

Each provider takes a single prompt and returns raw text (JSON expected).
JobMatcher owns parsing, retry, and fallback — providers just do I/O.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "key_hint": "AIzaSy...",
        "key_url": "https://aistudio.google.com/app/apikey",
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4o-mini",
        "key_hint": "sk-proj-... or sk-...",
        "key_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "default_model": "claude-haiku-4-5",
        "key_hint": "sk-ant-api03-...",
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    "grok": {
        "label": "xAI Grok",
        "default_model": "grok-2-latest",
        "key_hint": "xai-...",
        "key_url": "https://console.x.ai",
    },
}


class LLMProvider(Protocol):
    """A synchronous LLM backend."""

    name: str

    def generate(self, prompt: str) -> str:
        """Return the raw text completion for the given prompt."""
        ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        import google.generativeai as genai
        self.api_key = api_key
        self.model_name = model
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(model)

    def generate(self, prompt: str) -> str:
        resp = self._client.generate_content(prompt)
        return resp.text or ""


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self.api_key = api_key
        self.model_name = model
        self._client = OpenAI(api_key=api_key)

    def generate(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You return only valid JSON matching the requested schema. No prose, no markdown fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        import anthropic
        self.api_key = api_key
        self.model_name = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str) -> str:
        resp = self._client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""


class GrokProvider:
    """xAI exposes an OpenAI-compatible API at api.x.ai/v1."""
    name = "grok"

    def __init__(self, api_key: str, model: str = "grok-2-latest"):
        from openai import OpenAI
        self.api_key = api_key
        self.model_name = model
        self._client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

    def generate(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You return only valid JSON matching the requested schema. No prose, no markdown fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""


_FACTORY: dict[str, type] = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "grok": GrokProvider,
}


def build_provider(name: str, api_key: str, model: str | None = None) -> LLMProvider:
    """Factory — create a provider by canonical name."""
    key = (name or "gemini").strip().lower()
    if key not in _FACTORY:
        raise ValueError(f"Unknown LLM provider: {name!r}. Valid: {list(PROVIDERS)}")
    cls = _FACTORY[key]
    resolved_model = model or PROVIDERS[key]["default_model"]
    return cls(api_key=api_key, model=resolved_model)
