"""LLM client — supports opencode, claude, openai and any OpenAI-compatible endpoint."""

from __future__ import annotations
import json
import logging
from typing import Any

import httpx

from .config import config

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting opencode, claude, openai and custom providers.

    - opencode   → OpenAI-compatible local endpoint (default http://localhost:11434/v1)
    - claude     → Anthropic Messages API (https://api.anthropic.com/v1/messages)
    - openai     → OpenAI API (https://api.openai.com/v1/chat/completions)
    - custom     → any OpenAI-compatible endpoint
    """

    def __init__(
        self,
        provider: str = "opencode",
        api_key: str = "",
        base_url: str = "http://localhost:11434/v1",
        default_model: str = "llama3.2",
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ── OpenAI-compatible (opencode, openai, custom) ──────────────────────

    async def _chat_openai_compat(
        self,
        *,
        model: str | None = None,
        system: str | None = None,
        messages: list[dict[str, str] | str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        model = model or self.default_model
        msgs = messages or []
        normalised: list[dict[str, str]] = []
        for m in msgs:
            if isinstance(m, str):
                normalised.append({"role": "user", "content": m})
            else:
                normalised.append(m)
        body: dict[str, Any] = {
            "model": model,
            "messages": normalised,
            "temperature": temperature or 0.3,
            "max_tokens": max_tokens or 2048,
        }
        if system:
            body["messages"] = [{"role": "system", "content": system}] + normalised

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = await self._client.post("/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    # ── Claude / Anthropic ────────────────────────────────────────────────

    async def _chat_claude(
        self,
        *,
        model: str | None = None,
        system: str | None = None,
        messages: list[dict[str, str] | str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        model = model or self.default_model
        msgs = messages or []
        normalised: list[dict[str, str]] = []
        for m in msgs:
            if isinstance(m, str):
                normalised.append({"role": "user", "content": m})
            else:
                normalised.append(m)

        # Claude doesn't support system role inside messages array → pass as top-level
        body: dict[str, Any] = {
            "model": model,
            "messages": normalised,
            "temperature": temperature or 0.3,
            "max_tokens": max_tokens or 2048,
        }
        if system:
            body["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        resp = await self._client.post("/messages", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        # Claude returns content as a list of blocks
        content = data.get("content", [])
        if isinstance(content, list):
            parts = []
            for block in content:
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts).strip()
        return str(content).strip()

    # ── Unified chat ──────────────────────────────────────────────────────

    async def chat(
        self,
        *,
        model: str | None = None,
        system: str | None = None,
        messages: list[dict[str, str] | str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if self.provider == "claude":
            return await self._chat_claude(
                model=model, system=system, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
        # opencode / openai / custom → OpenAI-compatible
        return await self._chat_openai_compat(
            model=model, system=system, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def structured_chat(
        self,
        *,
        model: str | None = None,
        system: str | None = None,
        messages: list[dict[str, str] | str] | None = None,
        retries: int = 3,
    ) -> dict:
        for attempt in range(retries):
            raw = await self.chat(model=model, system=system, messages=messages or [])
            cleaned = raw.strip()
            # Try to extract JSON from possible markdown code blocks
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    continue
                raise
        raise RuntimeError("Failed to parse JSON response after retries")


# Singleton instance
_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient(
            provider=config.llm.provider,
            api_key=config.llm.api_key,
            base_url=config.llm.api_base,
            default_model=config.llm.default_model,
        )
    return _client