"""LLM client — wraps any OpenAI-compatible API (free models from freellmapi etc.)"""

from __future__ import annotations
import json
import logging
from typing import Any

import httpx

from .config import config

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI-compatible client for free models."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "http://127.0.0.1:3001/v1",
        default_model: str = "gemini-3.8-flash",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def close(self) -> None:
        await self._client.aclose()

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
        model = model or self.default_model
        msgs = messages or []
        # Normalise: strings become {"role":"user","content":s}
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
            api_key=config.llm.api_key,
            base_url=config.llm.api_base,
            default_model=config.llm.default_model,
        )
    return _client
