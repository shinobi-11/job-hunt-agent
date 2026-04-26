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


import time as _time

# Cache: provider → (model_list, expiry_epoch). 1-hour TTL per provider.
# Keyed by provider only — model lists are the same for all keys of a provider.
_MODEL_CACHE: dict[str, tuple[list[dict], float]] = {}
_MODEL_CACHE_TTL = 3600


def _wrap(items: list[tuple[str, str, bool]]) -> list[dict]:
    out = [{"id": i[0], "label": i[1], "recommended": i[2]} for i in items]
    out.sort(key=lambda x: (not x["recommended"], x["id"]))
    return out


async def list_models_async(provider: str, api_key: str) -> list[dict]:
    """Discover models for the given provider using async HTTP (httpx).
    Results are cached per provider for 1 hour so repeated calls are instant."""
    import httpx

    p = (provider or "gemini").strip().lower()

    cached = _MODEL_CACHE.get(p)
    if cached and _time.monotonic() < cached[1]:
        return cached[0]

    timeout = httpx.Timeout(connect=4.0, read=8.0, write=4.0, pool=4.0)
    result: list[dict] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        if p == "gemini":
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
            r.raise_for_status()
            models = []
            for m in r.json().get("models", []):
                if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                    continue
                mid = m.get("name", "").replace("models/", "")
                rec = mid in {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"}
                models.append((mid, m.get("displayName", mid), rec))
            result = _wrap(models)

        elif p == "openai":
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            r.raise_for_status()
            models = []
            for m in r.json().get("data", []):
                mid = m.get("id", "")
                if "gpt" not in mid.lower():
                    continue
                rec = mid in {"gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"}
                models.append((mid, mid, rec))
            result = _wrap(models)

        elif p == "anthropic":
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
            r.raise_for_status()
            models = []
            for m in r.json().get("data", []):
                mid = m.get("id", "")
                label = m.get("display_name", mid)
                rec = "haiku-4-5" in mid or "sonnet-4-6" in mid or "opus-4-7" in mid
                models.append((mid, label, rec))
            result = _wrap(models)

        elif p == "grok":
            r = await client.get(
                "https://api.x.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            r.raise_for_status()
            models = []
            for m in r.json().get("data", []):
                mid = m.get("id", "")
                rec = "grok-3" in mid or "grok-2" in mid
                models.append((mid, mid, rec))
            result = _wrap(models)

    if result:
        _MODEL_CACHE[p] = (result, _time.monotonic() + _MODEL_CACHE_TTL)
    return result


def list_models(provider: str, api_key: str) -> list[dict]:
    """Sync wrapper kept for compatibility — prefer list_models_async in async contexts."""
    import asyncio
    return asyncio.run(list_models_async(provider, api_key))
