"""Minimal MCP server over Streamable HTTP (JSON responses).

Flows with mcp_enabled are exposed as tools: tools/list and tools/call.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from . import __version__, db
from .components.base import slug
from .engine import Engine, FlowError

router = APIRouter()
PROTOCOL = "2025-06-18"


def _tools() -> list[dict[str, Any]]:
    with db.conn() as c:
        flows = db.rows(c.execute("SELECT * FROM flows WHERE mcp_enabled=1 ORDER BY name").fetchall(), ("data",))
    return flows


def tool_name(f: dict[str, Any]) -> str:
    return f.get("mcp_tool_name") or slug(f["name"])


def _result(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


async def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method, id_ = msg.get("method"), msg.get("id")
    params = msg.get("params") or {}
    if id_ is None:  # notification
        return None
    if method == "initialize":
        return _result(id_, {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "kelvo", "version": __version__},
        })
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": [{
            "name": tool_name(f),
            "description": f.get("mcp_description") or f["description"] or f["name"],
            "inputSchema": {"type": "object", "properties": {
                "input_value": {"type": "string", "description": "The message to send to the flow"},
                "session_id": {"type": "string", "description": "Optional session to continue"},
            }, "required": ["input_value"]},
        } for f in _tools()]})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        f = next((f for f in _tools() if tool_name(f) == name), None)
        if not f:
            return _error(id_, -32602, f"Unknown tool: {name}")
        try:
            res = await Engine(f, input_value=str(args.get("input_value", "")), session_id=args.get("session_id")).run()
        except FlowError as e:
            return _result(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        texts = [o["message"]["text"] if o["type"] == "chat" else o["text"] for o in res["outputs"]]
        return _result(id_, {"content": [{"type": "text", "text": "\n\n".join(texts) or "(no output)"}], "isError": False})
    return _error(id_, -32601, f"Method not found: {method}")


def _auth_dep():
    from .main import require_api_key
    return require_api_key


@router.post("/mcp", dependencies=[Depends(_auth_dep())])
async def mcp_post(request: Request) -> Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)
    if isinstance(body, list):
        out = [r for r in [await handle(m) for m in body] if r is not None]
        return JSONResponse(out) if out else Response(status_code=202)
    r = await handle(body)
    return JSONResponse(r) if r is not None else Response(status_code=202)


@router.get("/mcp")
async def mcp_get() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})
