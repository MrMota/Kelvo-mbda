"""Tools that make agents useful on your own machine: web search, files, command line."""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import asyncio
import httpx

from .base import DATA, TEXT, Component, Field, Output, ToolDef

# Tests swap this for an httpx.MockTransport; normally None (real network).
TRANSPORT: httpx.AsyncBaseTransport | None = None
UA = "Mozilla/5.0 (compatible; Kelvo/0.2; +local agent)"


def default_workspace() -> Path:
    return Path(os.environ.get("KELVO_WORKSPACE") or (Path.home() / "KelvoWorkspace"))


def workspace_of(ctx) -> Path:
    raw = ctx.engine.substitute(str(ctx.params.get("workspace") or "")).strip()
    root = Path(raw).expanduser() if raw else default_workspace()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def inside(root: Path, rel: str) -> Path:
    """Resolve rel inside root; refuse anything that ends up outside (.., absolute paths, symlinks)."""
    rel = (rel or ".").strip()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise PermissionError(f"'{rel}' is outside the workspace {root}. Use paths inside it, like 'notes/todo.md'.")
    return p


# ---------------------------------------------------------------- web search

def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_duckduckgo(page: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    starts = [(m.start(), m.group(1).split()) for m in re.finditer(r'<div[^>]+class="([^"]*)"', page)
              if "result" in m.group(1).split()]
    for i, (pos, classes) in enumerate(starts):
        if "result--ad" in classes:
            continue
        b = page[pos:starts[i + 1][0] if i + 1 < len(starts) else len(page)]
        a = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not a:
            continue
        href = html.unescape(a.group(1))
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href if "://" in href else "https:" + href).query).get("uddg", [href])[0])
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', b, re.S)
        out.append({"title": _strip(a.group(2)), "url": href, "snippet": _strip(sn.group(1)) if sn else ""})
    return out


async def search(provider: str, query: str, n: int, api_key: str = "", searxng_url: str = "") -> list[dict[str, str]]:
    async with httpx.AsyncClient(transport=TRANSPORT, timeout=20, headers={"User-Agent": UA}, follow_redirects=True) as c:
        if provider == "brave":
            if not api_key:
                raise ValueError("Brave needs an API key (api-dashboard.search.brave.com). Put it in a global variable, e.g. ${BRAVE_API_KEY}.")
            r = await c.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": n},
                            headers={"X-Subscription-Token": api_key, "Accept": "application/json"})
            r.raise_for_status()
            items = (r.json().get("web") or {}).get("results") or []
            return [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": _strip(i.get("description", ""))} for i in items][:n]
        if provider == "tavily":
            if not api_key:
                raise ValueError("Tavily needs an API key (tavily.com). Put it in a global variable, e.g. ${TAVILY_API_KEY}.")
            r = await c.post("https://api.tavily.com/search", json={"query": query, "max_results": n},
                             headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("content", "")} for i in r.json().get("results", [])][:n]
        if provider == "searxng":
            if not searxng_url:
                raise ValueError("Set the SearXNG URL (your instance, with the JSON format enabled).")
            r = await c.get(f"{searxng_url.rstrip('/')}/search", params={"q": query, "format": "json"})
            r.raise_for_status()
            return [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("content", "")} for i in r.json().get("results", [])][:n]
        r = await c.post("https://html.duckduckgo.com/html/", data={"q": query})
        r.raise_for_status()
        return parse_duckduckgo(r.text)[:n]


class WebSearch(Component):
    key = "WebSearch"
    display = "Web Search"
    category = "Tools"
    description = "Search the web and get titles, links and snippets. Pair it with the URL tool to read a result."
    icon = "search"
    tool_default = True
    tool_output = "text"
    fields = [
        Field("query", "Query", "str", "", tool_param=True, required=True, info="What to search the web for"),
        Field("provider", "Search with", "select", "duckduckgo", options=["duckduckgo", "brave", "tavily", "searxng"],
              info="DuckDuckGo needs no key. Brave and Tavily need a free API key; SearXNG is your own instance."),
        Field("api_key", "API key", "secret", "", placeholder="${BRAVE_API_KEY}", advanced=True,
              info="Brave or Tavily key. Use a global variable (Settings → Global variables), e.g. ${TAVILY_API_KEY}."),
        Field("searxng_url", "SearXNG URL", "str", "", placeholder="http://127.0.0.1:8888", advanced=True),
        Field("max_results", "Results", "int", 5, advanced=True),
    ]
    outputs = [Output("text", "Results", TEXT), Output("results", "Results (Data)", DATA)]

    async def out_results(self, ctx) -> list[dict[str, str]]:
        q = (await ctx.text("query")).strip()
        if not q:
            return []
        return await search(await ctx.text("provider", "duckduckgo") or "duckduckgo", q,
                            max(1, min(20, int(await ctx.get("max_results", 5)))),
                            api_key=await ctx.text("api_key"), searxng_url=await ctx.text("searxng_url"))

    async def out_text(self, ctx) -> str:
        res = await self.out_results(ctx)
        if not res:
            return "No results."
        return "\n\n".join(f"{i}. {r['title']}\n{r['url']}\n{r['snippet']}" for i, r in enumerate(res, 1))


# ---------------------------------------------------------------- files

MAX_READ = 20000
MAX_WRITE = 1_000_000


class Files(Component):
    key = "Files"
    display = "Files"
    category = "Tools"
    description = ("Read, write and edit files in one workspace folder. As a tool it gives the agent "
                   "list_files, read_file, write_file and edit_file. Nothing outside the folder can be touched.")
    icon = "folder"
    tool_default = True
    fields = [
        Field("workspace", "Workspace folder", "str", "", placeholder="~/KelvoWorkspace",
              info="Blank = KelvoWorkspace in your user folder (or KELVO_WORKSPACE)."),
        Field("read_only", "Read only", "bool", False, info="Only list and read; no writing or editing."),
        Field("approve_writes", "Ask before writing", "bool", False, advanced=True,
              info="Each write or edit waits for your Approve in the Playground."),
    ]
    outputs = [Output("listing", "File list", TEXT)]

    @staticmethod
    def _list(root: Path, rel: str) -> str:
        base = inside(root, rel)
        if not base.exists():
            return f"'{rel}' does not exist. The workspace is {root}."
        if base.is_file():
            return f"{rel} (file, {base.stat().st_size} bytes)"
        rows = []
        for p in sorted(base.rglob("*")):
            if len(rows) >= 300:
                rows.append("… (more files not shown)")
                break
            if any(part.startswith(".") for part in p.relative_to(root).parts):
                continue
            r = p.relative_to(root).as_posix()
            rows.append(f"{r}/" if p.is_dir() else f"{r}  ({p.stat().st_size} bytes)")
        return "\n".join(rows) or "(empty)"

    async def out_listing(self, ctx) -> str:
        return self._list(workspace_of(ctx), ".")

    def toolset(self, ctx) -> list[ToolDef]:
        root = workspace_of(ctx)
        read_only = bool(ctx.params.get("read_only"))
        approve = bool(ctx.params.get("approve_writes"))

        async def list_files(a: dict[str, Any]) -> str:
            return self._list(root, str(a.get("path") or "."))

        async def read_file(a: dict[str, Any]) -> str:
            p = inside(root, str(a.get("path", "")))
            if not p.is_file():
                return f"No file '{a.get('path')}'. Use list_files to see what exists."
            text = p.read_text(encoding="utf-8", errors="replace")
            start = max(0, int(a.get("start", 0) or 0))
            chunk = text[start:start + MAX_READ]
            more = f"\n\n[… {len(text) - start - len(chunk)} more characters; call read_file with start={start + len(chunk)}]" if start + len(chunk) < len(text) else ""
            return chunk + more

        async def gate(what: str, details: dict[str, Any]) -> str | None:
            if read_only:
                return "This Files tool is read-only."
            if approve and not await ctx.engine.ask_approval(ctx.node_id, "files", what, details):
                return f"The user did not approve: {what}"
            return None

        async def write_file(a: dict[str, Any]) -> str:
            rel, content = str(a.get("path", "")), str(a.get("content", ""))
            if len(content) > MAX_WRITE:
                return f"Too large ({len(content)} characters, limit {MAX_WRITE})."
            p = inside(root, rel)
            if (msg := await gate(f"write {rel}", {"path": rel, "characters": len(content)})):
                return msg
            p.parent.mkdir(parents=True, exist_ok=True)
            existed = p.exists()
            p.write_text(content, encoding="utf-8")
            return f"{'Overwrote' if existed else 'Created'} {rel} ({len(content)} characters)."

        async def edit_file(a: dict[str, Any]) -> str:
            rel, old, new = str(a.get("path", "")), str(a.get("old_text", "")), str(a.get("new_text", ""))
            p = inside(root, rel)
            if not p.is_file():
                return f"No file '{rel}'. Create it with write_file."
            if not old:
                return "old_text is empty. Copy the exact text to replace from read_file."
            text = p.read_text(encoding="utf-8", errors="replace")
            n = text.count(old)
            if n == 0:
                return "old_text was not found. Read the file again and copy the text exactly, including spaces."
            if n > 1 and not a.get("replace_all"):
                return f"old_text appears {n} times. Include more surrounding text to make it unique, or set replace_all."
            if (msg := await gate(f"edit {rel}", {"path": rel, "replacing": old[:300], "with": new[:300]})):
                return msg
            p.write_text(text.replace(old, new) if a.get("replace_all") else text.replace(old, new, 1), encoding="utf-8")
            return f"Edited {rel} ({n if a.get('replace_all') else 1} replacement{'s' if a.get('replace_all') and n > 1 else ''})."

        s = lambda **props: {"type": "object", "properties": props, "required": [k for k, v in props.items() if v.pop("_req", False)]}  # noqa: E731
        tools = [
            ToolDef("list_files", f"List files and folders in the workspace ({root}).",
                    s(path={"type": "string", "description": "Folder inside the workspace; '.' for all"}), list_files),
            ToolDef("read_file", "Read a text file from the workspace.",
                    s(path={"type": "string", "description": "File path inside the workspace", "_req": True},
                      start={"type": "integer", "description": "Character offset to continue from"}), read_file),
        ]
        if not read_only:
            tools += [
                ToolDef("write_file", "Create or overwrite a text file in the workspace.",
                        s(path={"type": "string", "description": "File path inside the workspace", "_req": True},
                          content={"type": "string", "description": "The full file content", "_req": True}), write_file),
                ToolDef("edit_file", "Replace exact text in a workspace file. Read the file first and copy old_text exactly.",
                        s(path={"type": "string", "description": "File path inside the workspace", "_req": True},
                          old_text={"type": "string", "description": "Exact text to replace (must be unique)", "_req": True},
                          new_text={"type": "string", "description": "Replacement text", "_req": True},
                          replace_all={"type": "boolean", "description": "Replace every occurrence"}), edit_file),
            ]
        return tools


# ---------------------------------------------------------------- command line

MAX_OUTPUT = 8000


class Shell(Component):
    key = "Shell"
    display = "Command Line"
    category = "Tools"
    description = "Run a command in the workspace folder and get its output. Asks you to approve each command first."
    icon = "terminal"
    tool_default = True
    tool_output = "output"
    fields = [
        Field("command", "Command", "str", "", tool_param=True, required=True,
              info="The command to run, e.g. 'dir' on Windows or 'ls -la' on Linux/macOS"),
        Field("workspace", "Working folder", "str", "", placeholder="~/KelvoWorkspace", info="Blank = the Files workspace."),
        Field("shell", "Shell", "select", "default", options=["default", "powershell"],
              info="default = cmd on Windows, sh on Linux/macOS."),
        Field("timeout", "Timeout (seconds)", "int", 60, advanced=True),
        Field("require_approval", "Ask before every command", "bool", True,
              info="Strongly recommended. Commands run with your user's full permissions."),
    ]
    outputs = [Output("output", "Output", TEXT)]

    async def out_output(self, ctx) -> str:
        cmd = (await ctx.text("command")).strip()
        if not cmd:
            return "No command given."
        root = workspace_of(ctx)
        shell = await ctx.text("shell", "default") or "default"
        if await ctx.get("require_approval", True):
            ok = await ctx.engine.ask_approval(ctx.node_id, "command line", cmd, {"command": cmd, "folder": str(root), "shell": shell})
            if not ok:
                return (f"The user did not approve running: {cmd}" if ctx.engine.interactive
                        else "Commands need approval, and nobody is watching this run (API/MCP). Not run.")
        timeout = max(1, min(3600, int(await ctx.get("timeout", 60))))
        if shell == "powershell":
            argv: Any = ["powershell" if sys.platform == "win32" else "pwsh", "-NoProfile", "-Command", cmd]
            use_shell = False
        else:
            argv, use_shell = cmd, True

        def run() -> subprocess.CompletedProcess:
            return subprocess.run(argv, shell=use_shell, cwd=root, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)

        try:
            r = await asyncio.to_thread(run)
        except subprocess.TimeoutExpired:
            return f"Timed out after {timeout} s and was stopped: {cmd}"
        except FileNotFoundError as e:
            return f"Could not start the shell: {e}"
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + f"\n[… output cut at {MAX_OUTPUT} characters]"
        return f"$ {cmd}\n(exit code {r.returncode})\n{out.strip()}"


# ---------------------------------------------------------------- MCP servers

def _json_param(ctx, name: str) -> dict[str, str]:
    raw = ctx.engine.substitute(str(ctx.params.get(name) or "").strip())
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be JSON, like {{\"x-api-key\": \"${{MY_KEY}}\"}}") from e
    if not isinstance(val, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(k): str(v) for k, v in val.items()}


def _tool_name(prefix: str, name: str) -> str:
    return (re.sub(r"[^A-Za-z0-9_-]", "_", prefix + name) or "tool")[:64]


class MCPTools(Component):
    key = "MCPTools"
    display = "MCP Tools"
    category = "Tools"
    description = ("Give an agent the tools of any MCP server: an HTTP URL, or a local command such as "
                   "'npx -y @modelcontextprotocol/server-filesystem C:\\\\notes'.")
    icon = "plug"
    tool_default = True
    fields = [
        Field("transport", "Server type", "select", "http", options=["http", "command"],
              info="http = a URL (Streamable HTTP). command = a program Kelvo starts on this PC (stdio)."),
        Field("url", "Server URL", "str", "", placeholder="http://127.0.0.1:8000/mcp"),
        Field("headers", "Headers (JSON)", "json", "", placeholder='{"Authorization": "Bearer ${MY_TOKEN}"}', advanced=True,
              info="Sent with every request; use global variables for keys."),
        Field("command", "Command", "str", "", placeholder="npx -y @modelcontextprotocol/server-filesystem C:\\notes",
              info="For server type 'command'. Needs Node (npx) or uv (uvx) installed for most servers."),
        Field("env", "Environment (JSON)", "json", "", placeholder='{"GITHUB_TOKEN": "${GITHUB_TOKEN}"}', advanced=True),
        Field("only", "Only these tools", "str", "", advanced=True, placeholder="read_file, search",
              info="Comma-separated tool names; blank = all."),
        Field("prefix", "Tool name prefix", "str", "", advanced=True, placeholder="gh_",
              info="Avoids name clashes when an agent uses several servers."),
        Field("require_approval", "Ask before every call", "bool", False,
              info="Each call waits for your Approve in the Playground. Unattended runs then can't use these tools."),
        Field("timeout", "Timeout (seconds)", "int", 60, advanced=True),
    ]
    outputs = [Output("tools", "Available tools", TEXT)]

    async def _connect(self, ctx):
        from ..mcp_client import HTTPClient, MCPError, StdioClient

        timeout = max(5, min(600, int(ctx.params.get("timeout") or 60)))
        if (ctx.params.get("transport") or "http") == "command":
            cmd = ctx.engine.substitute(str(ctx.params.get("command") or "")).strip()
            ws = default_workspace()
            ws.mkdir(parents=True, exist_ok=True)  # servers start in the workspace; it may not exist yet
            client = StdioClient(cmd, env=_json_param(ctx, "env"), cwd=str(ws), timeout=timeout)
        else:
            url = ctx.engine.substitute(str(ctx.params.get("url") or "")).strip()
            if not url.startswith(("http://", "https://")):
                raise MCPError("Set the MCP server URL (http:// or https://).")
            client = HTTPClient(url, headers=_json_param(ctx, "headers"), timeout=timeout)
        ctx.engine.closers.append(client.close)
        await client.start()
        tools = await client.list_tools()
        only = {t.strip() for t in str(ctx.params.get("only") or "").split(",") if t.strip()}
        if only:
            tools = [t for t in tools if t.get("name") in only]
        return client, tools

    async def out_tools(self, ctx) -> str:
        _, tools = await self._connect(ctx)
        if not tools:
            return "Connected. The server offers no tools."
        return "\n".join(f"- {t['name']}: {(t.get('description') or '').strip()[:200]}" for t in tools)

    async def toolset(self, ctx) -> list[ToolDef]:
        client, tools = await self._connect(ctx)
        prefix = str(ctx.params.get("prefix") or "")
        approve = bool(ctx.params.get("require_approval"))
        out: list[ToolDef] = []
        for t in tools:
            real = t["name"]

            async def call(args: dict[str, Any], real: str = real) -> str:
                if approve and not await ctx.engine.ask_approval(
                        ctx.node_id, "MCP tool", f"{real}({json.dumps(args, ensure_ascii=False)[:400]})", {"tool": real, "arguments": args}):
                    return f"The user did not approve calling {real}."
                return await client.call_tool(real, args)

            schema = t.get("inputSchema") or {"type": "object", "properties": {}}
            schema.setdefault("type", "object")
            out.append(ToolDef(_tool_name(prefix, real), (t.get("description") or real).strip()[:1000], schema, call))
        return out
