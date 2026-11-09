"""Thin async client for the Ollama HTTP API."""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

TIMEOUT = float(os.environ.get("KELVO_OLLAMA_TIMEOUT", "600"))


class OllamaError(RuntimeError):
    pass


def _client(timeout: float | None) -> httpx.AsyncClient:
    """httpx client with the optional Ollama API key (Settings → Models) as a Bearer token."""
    from . import db  # local import: db has no dependency on this module

    key = db.get_setting("ollama_api_key") or os.environ.get("OLLAMA_API_KEY") or ""
    return httpx.AsyncClient(timeout=timeout, headers={"Authorization": f"Bearer {key}"} if key else None)


_caps_cache: dict[tuple[str, str, str], list[str] | None] = {}


async def capabilities(base_url: str, model: str, version: str = "") -> list[str] | None:
    """What a model can do, from /api/show (Ollama ≥ 0.6 reports e.g. completion, tools,
    vision, embedding). None if this Ollama doesn't say. Cached per model version, so a
    model list is one /api/show per model, once."""
    key = (base_url, model, version)
    if key in _caps_cache:
        return _caps_cache[key]
    try:
        async with _client(10) as client:
            r = await client.post(f"{base_url}/api/show", json={"model": model})
        caps = r.json().get("capabilities") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None  # don't cache transient failures
    _caps_cache[key] = caps if isinstance(caps, list) else None
    return _caps_cache[key]


def _err(resp: httpx.Response, body: bytes) -> OllamaError:
    try:
        msg = json.loads(body).get("error", body.decode())
    except Exception:
        msg = body.decode(errors="replace")
    if "does not support thinking" in msg:
        msg += " — turn off 'Think before answering' on this Agent, or pick a reasoning model such as qwen3."
    if "does not support tools" in msg:
        msg += " — this model can't call tools. Pick one that can, such as qwen3, llama3.1 or mistral-nemo."
    if resp.status_code == 404 and "not found" in msg:
        msg += " — this model isn't on your Ollama yet. Pull it in Settings → Models, or run `ollama pull <model>`."
    return OllamaError(f"Ollama error {resp.status_code}: {msg}")


async def list_models(base_url: str) -> list[dict[str, Any]]:
    async with _client(10) as client:
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
    think: bool | None = None,
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
    if think is not None:
        payload["think"] = think  # reasoning models (qwen3, deepseek-r1…) think first; the thinking streams separately
    try:
        async with _client(TIMEOUT) as client:
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
        raise OllamaError(f"Can't reach Ollama at {base_url}. Start it with `ollama serve`, or fix the URL in Settings → Models.") from e


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
        async with _client(TIMEOUT) as client:
            r = await client.post(f"{base_url}/api/embed", json={"model": model, "input": texts})
            if r.status_code != 200:
                raise _err(r, r.content)
            return r.json()["embeddings"]
    except httpx.ConnectError as e:
        raise OllamaError(f"Can't reach Ollama at {base_url}. Start it with `ollama serve`, or fix the URL in Settings → Models.") from e


async def pull(base_url: str, model: str) -> AsyncIterator[dict[str, Any]]:
    async with _client(None) as client:
        async with client.stream("POST", f"{base_url}/api/pull", json={"model": model, "stream": True}) as r:
            if r.status_code != 200:
                raise _err(r, await r.aread())
            async for line in r.aiter_lines():
                if line.strip():
                    yield json.loads(line)
