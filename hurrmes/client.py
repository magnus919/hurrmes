"""HTTP client for the Hermes API Server."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from hurrmes.config import Config


class HermesClient:
    """Client for the Hermes API Server (OpenAI-compatible chat completions)."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.base_url = config.server.base_url
        self.api_key = config.server.api_key
        self._session_id: str | None = None

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if self._session_id:
            h["X-Hermes-Session-Id"] = self._session_id
        return h

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str = "hermes-agent",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a chat completion from the Hermes API Server.

        Yields dicts with keys:
          - type: "delta" | "done" | "error"
          - content: str (for delta)
          - usage: dict (for done)
          - session_id: str (for done)
        """
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            start = time.monotonic()
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._headers(),
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        yield {
                            "type": "error",
                            "content": f"HTTP {resp.status_code}: {error_text.decode(errors='replace')}",
                        }
                        return

                    usage = {}
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        # Delta content
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield {"type": "delta", "content": delta}

                        # Usage (may appear mid-stream or on last chunk)
                        if chunk.get("usage"):
                            usage = chunk["usage"]

                    # Session ID from headers (set once after stream completes)
                    if "X-Hermes-Session-Id" in resp.headers:
                        self._session_id = resp.headers["X-Hermes-Session-Id"]

                    elapsed = time.monotonic() - start
                    yield {
                        "type": "done",
                        "usage": usage,
                        "session_id": self._session_id or "",
                        "elapsed": elapsed,
                    }

            except httpx.ConnectError as e:
                yield {
                    "type": "error",
                    "content": f"Cannot connect to Hermes API at {self.base_url}: {e}",
                }
            except httpx.TimeoutException:
                yield {
                    "type": "error",
                    "content": "Request timed out after 120s",
                }

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str = "hermes-agent",
    ) -> dict[str, Any]:
        """Non-streaming chat completion. Returns final response dict."""
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._headers(),
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                if "X-Hermes-Session-Id" in resp.headers:
                    self._session_id = resp.headers["X-Hermes-Session-Id"]
                return data  # type: ignore[no-any-return]
            except httpx.HTTPStatusError as e:
                return {"error": str(e), "status": e.response.status_code}
            except httpx.ConnectError as e:
                return {"error": f"Cannot connect: {e}"}

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str | None) -> None:
        self._session_id = value
