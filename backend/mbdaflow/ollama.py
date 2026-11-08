"""Thin async client for the Ollama HTTP API."""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

TIMEOUT = float(os.environ.get("MBDAFLOW_OLLAMA_TIMEOUT", "600"))


class OllamaError(RuntimeError):
    pass


def _err(resp: httpx.Response, body: bytes) -> OllamaError:
    try:
        msg = json.loads(body).get("error", body.decode())
    except Exception:
        msg = body.decode(errors="replace")
    if "does not support tools" in msg:
        msg += " — pick a tool-capable model such as llama3.1, qwen2.5 / qwen3 or mistral-nemo."
    if resp.status_code == 404 and "not found" in msg:
        msg += " — pull it first (Settings → Models, or `ollama pull <model>`)."
    return OllamaError(f"Ollama error {resp.status_code}: {msg}")


async def list_models(base_url: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{base_url}/api/tags")
        if r.status_code != 200:
            raise _err(r, r.content)
        return r.json().get("models", [])


async def chat_stream(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
    fmt: Any = None,
    keep_alive: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields Ollama /api/chat stream chunks."""
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    if tools:
        payload["tools"] = tools
    if options:
        payload["options"] = options
    if fmt:
        payload["format"] = fmt
    if keep_alive:
        payload["keep_alive"] = keep_alive
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", f"{base_url}/api/chat", json=payload) as r:
                if r.status_code != 200:
                    raise _err(r, await r.aread())
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise OllamaError(f"Ollama error: {chunk['error']}")
                    yield chunk
    except httpx.ConnectError as e:
        raise OllamaError(f"Cannot reach Ollama at {base_url}. Is `ollama serve` running?") from e


async def chat(base_url: str, model: str, messages: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    """Non-streaming convenience: returns {'content', 'tool_calls'}."""
    content, tool_calls = "", []
    async for ch in chat_stream(base_url, model, messages, **kw):
        m = ch.get("message") or {}
        content += m.get("content") or ""
        tool_calls += m.get("tool_calls") or []
    return {"content": content, "tool_calls": tool_calls}


async def embed(base_url: str, model: str, texts: list[str]) -> list[list[float]]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{base_url}/api/embed", json={"model": model, "input": texts})
            if r.status_code != 200:
                raise _err(r, r.content)
            return r.json()["embeddings"]
    except httpx.ConnectError as e:
        raise OllamaError(f"Cannot reach Ollama at {base_url}. Is `ollama serve` running?") from e


async def pull(base_url: str, model: str) -> AsyncIterator[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{base_url}/api/pull", json={"model": model, "stream": True}) as r:
            if r.status_code != 200:
                raise _err(r, await r.aread())
            async for line in r.aiter_lines():
                if line.strip():
                    yield json.loads(line)
