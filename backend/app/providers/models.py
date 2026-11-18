"""Real HTTP model-provider adapters; credentials are read only from environment."""
import os
from typing import Protocol

import httpx


class ModelProviderError(RuntimeError):
    """Raised when a configured model provider cannot complete a request."""


class ModelProvider(Protocol):
    async def complete(self, prompt: str) -> str: ...


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    async def complete(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                return str(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderError("OpenAI-compatible provider request failed") from exc


class AnthropicProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key, self.model = api_key, model

    async def complete(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model, "max_tokens": 2048,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                return str(response.json()["content"][0]["text"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderError("Anthropic provider request failed") from exc


def configured_provider(name: str) -> ModelProvider:
    if name == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ModelProviderError("OPENAI_API_KEY is not configured")
        return OpenAICompatibleProvider(
            key, os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    if name == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ModelProviderError("ANTHROPIC_API_KEY is not configured")
        return AnthropicProvider(key, os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"))
    raise ModelProviderError("Unsupported model provider")
