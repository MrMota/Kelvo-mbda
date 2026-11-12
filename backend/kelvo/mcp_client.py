"""Minimal MCP client: lets Kelvo agents use tools from other MCP servers.

Two transports:
- Streamable HTTP: JSON-RPC POSTs to a URL; replies are JSON or an SSE stream.
- stdio: Kelvo starts the server program and exchanges newline-delimited JSON-RPC on its
  stdin/stdout. Done with a reader thread so it works the same on every OS and event loop.

Only what agents need: initialize, tools/list (paged), tools/call.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import os
import shlex
import shutil
import subprocess
import threading
from typing import Any

import httpx

PROTOCOL = "2025-06-18"
CLIENT_INFO = {"name": "kelvo", "version": "0.4"}


class MCPError(RuntimeError):
    pass


class _Base:
    def __init__(self, timeout: float):
        self.timeout = timeout
        self._ids = itertools.count(1)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        raise NotImplementedError

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    async def start(self) -> dict[str, Any]:
        info = await self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT_INFO})
        await self.notify("notifications/initialized")
        return info

    async def list_tools(self) -> list[dict[str, Any]]:
        tools, cursor = [], None
        for _ in range(50):  # pages
            res = await self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools", [])
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        res = await self.request("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for c in res.get("content", []):
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif c.get("type") == "resource":
                r = c.get("resource", {})
                parts.append(r.get("text") or f"[resource {r.get('uri', '')}]")
            else:
                parts.append(f"[{c.get('type')} content]")
        if res.get("structuredContent") is not None and not parts:
            parts.append(json.dumps(res["structuredContent"], ensure_ascii=False))
        text = "\n".join(parts) or "(no output)"
        return f"Tool error: {text}" if res.get("isError") else text

    async def close(self) -> None:
        return None

    @staticmethod
    def _unwrap(msg: dict[str, Any]) -> Any:
        if "error" in msg:
            e = msg["error"]
            raise MCPError(f"MCP server error {e.get('code')}: {e.get('message')}")
        return msg.get("result", {})


class HTTPClient(_Base):
    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float = 60):
        super().__init__(timeout)
        self.url = url
        self.headers = {"Accept": "application/json, text/event-stream", **(headers or {})}
        self.session: str | None = None
        self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    def _h(self) -> dict[str, str]:
        h = dict(self.headers)
        if self.session:
            h["Mcp-Session-Id"] = self.session
        h["MCP-Protocol-Version"] = PROTOCOL
        return h

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        rid = next(self._ids)
        body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        try:
            async with self.client.stream("POST", self.url, json=body, headers=self._h()) as r:
                if r.status_code in (401, 403):
                    raise MCPError(f"The MCP server refused access ({r.status_code}). Check the headers (API key).")
                if r.status_code >= 400:
                    raise MCPError(f"MCP server returned {r.status_code}: {(await r.aread())[:300].decode(errors='replace')}")
                self.session = r.headers.get("mcp-session-id", self.session)
                if "text/event-stream" in r.headers.get("content-type", ""):
                    async for line in r.aiter_lines():
                        if line.startswith("data:"):
                            msg = json.loads(line[5:].strip() or "{}")
                            if msg.get("id") == rid:
                                return self._unwrap(msg)
                    raise MCPError("The MCP server closed the stream without answering.")
                return self._unwrap(json.loads(await r.aread()))
        except httpx.ConnectError as e:
            raise MCPError(f"Can't reach the MCP server at {self.url}.") from e

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        try:
            await self.client.post(self.url, json={"jsonrpc": "2.0", "method": method, "params": params or {}}, headers=self._h())
        except httpx.HTTPError:
            pass

    async def close(self) -> None:
        await self.client.aclose()


class StdioClient(_Base):
    def __init__(self, command: str, env: dict[str, str] | None = None, cwd: str | None = None, timeout: float = 60):
        super().__init__(timeout)
        argv = shlex.split(command, posix=os.name != "nt")
        if not argv:
            raise MCPError("Set the command that starts the MCP server.")
        exe = shutil.which(argv[0])  # finds npx.cmd / uvx.exe on Windows
        if not exe:
            raise MCPError(f"'{argv[0]}' was not found. Install it, or use its full path.")
        argv[0] = exe
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         env={**os.environ, **(env or {})}, cwd=cwd, bufsize=0)
        except OSError as e:
            raise MCPError(f"Could not start the MCP server: {e}") from e
        self.loop = asyncio.get_running_loop()
        self.pending: dict[int, asyncio.Future] = {}
        self.stderr_tail: list[str] = []
        self.write_lock = threading.Lock()
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        for raw in iter(self.proc.stdout.readline, b""):
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue  # servers sometimes print banners; ignore non-JSON lines
            fut = self.pending.pop(msg.get("id"), None) if isinstance(msg, dict) else None
            if fut is not None:
                self.loop.call_soon_threadsafe(lambda f=fut, m=msg: f.done() or f.set_result(m))
        err = MCPError("The MCP server stopped. " + " ".join(self.stderr_tail[-3:]).strip())
        for fut in list(self.pending.values()):
            self.loop.call_soon_threadsafe(lambda f=fut: f.done() or f.set_exception(err))
        self.pending.clear()

    def _read_stderr(self) -> None:
        for raw in iter(self.proc.stderr.readline, b""):
            self.stderr_tail = (self.stderr_tail + [raw.decode("utf-8", "replace").strip()])[-20:]

    def _send(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj) + "\n").encode()
        with self.write_lock:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        rid = next(self._ids)
        fut: asyncio.Future = self.loop.create_future()
        self.pending[rid] = fut
        try:
            await asyncio.to_thread(self._send, {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        except OSError as e:
            self.pending.pop(rid, None)
            raise MCPError("The MCP server stopped. " + " ".join(self.stderr_tail[-3:]).strip()) from e
        try:
            msg = await asyncio.wait_for(fut, timeout=self.timeout)
        except asyncio.TimeoutError:
            self.pending.pop(rid, None)
            raise MCPError(f"The MCP server didn't answer '{method}' within {int(self.timeout)} s.")
        return self._unwrap(msg)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        try:
            await asyncio.to_thread(self._send, {"jsonrpc": "2.0", "method": method, "params": params or {}})
        except OSError:
            pass

    async def close(self) -> None:
        def stop() -> None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
        await asyncio.to_thread(stop)
