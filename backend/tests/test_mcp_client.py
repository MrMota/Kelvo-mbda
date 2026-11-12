import asyncio
import json
import socket
import sys
import textwrap
import threading
import time

import pytest

from kelvo.mcp_client import HTTPClient, MCPError, StdioClient

STDIO_SERVER = textwrap.dedent('''
    import json, sys
    print("starting test server (not JSON)", flush=True)
    for line in sys.stdin:
        m = json.loads(line)
        if "id" not in m:
            continue
        meth, p = m["method"], m.get("params", {})
        if meth == "initialize":
            r = {"protocolVersion": p["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "t", "version": "1"}}
        elif meth == "tools/list":
            if not p.get("cursor"):
                r = {"tools": [{"name": "echo", "description": "Echo text back", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}], "nextCursor": "page2"}
            else:
                r = {"tools": [{"name": "fail", "description": "Always fails", "inputSchema": {"type": "object", "properties": {}}}]}
        elif meth == "tools/call":
            a = p["arguments"]
            if p["name"] == "echo":
                r = {"content": [{"type": "text", "text": "echo: " + a.get("text", a.get("input", ""))}]}
            else:
                r = {"content": [{"type": "text", "text": "nope"}], "isError": True}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "no"}}), flush=True); continue
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}), flush=True)
''')


@pytest.fixture()
def stdio_cmd(tmp_path):
    script = tmp_path / "mcp_server.py"
    script.write_text(STDIO_SERVER)
    return f'"{sys.executable}" "{script}"'


def test_stdio_client(stdio_cmd):
    async def go():
        c = StdioClient(stdio_cmd, timeout=10)
        try:
            info = await c.start()
            tools = await c.list_tools()
            return info, [t["name"] for t in tools], await c.call_tool("echo", {"text": "hi"}), await c.call_tool("fail", {})
        finally:
            await c.close()
    info, names, out, err = asyncio.run(go())
    assert info["serverInfo"]["name"] == "t" and names == ["echo", "fail"]  # both pages
    assert out == "echo: hi" and err == "Tool error: nope"


def test_stdio_missing_program():
    async def go():
        StdioClient("definitely-not-a-program-xyz --flag")
    with pytest.raises(MCPError, match="was not found"):
        asyncio.run(go())


@pytest.fixture(scope="module")
def http_server():
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse

    app = FastAPI()
    seen = {"sessions": []}

    @app.post("/mcp")
    async def mcp(req: Request):
        m = await req.json()
        seen["sessions"].append(req.headers.get("mcp-session-id"))
        if "id" not in m:
            return Response(status_code=202)
        if m["method"] == "initialize":
            return JSONResponse({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "h", "version": "1"}}},
                                headers={"Mcp-Session-Id": "sess-1"})
        if m["method"] == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [{"name": "weather", "description": "Weather for a city", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}}}]}})
        async def sse():  # tools/call answered as an SSE stream, with a notification first
            yield "event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}) + "\n\n"
            yield "event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "Sunny in " + m["params"]["arguments"]["city"]}]}}) + "\n\n"
        return StreamingResponse(sse(), media_type="text/event-stream")

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp", seen
    server.should_exit = True


def test_http_client_json_sse_and_session(http_server):
    url, seen = http_server
    async def go():
        c = HTTPClient(url, timeout=10)
        try:
            await c.start()
            tools = await c.list_tools()
            return tools, await c.call_tool("weather", {"city": "Lisbon"})
        finally:
            await c.close()
    tools, out = asyncio.run(go())
    assert tools[0]["name"] == "weather" and out == "Sunny in Lisbon"
    assert seen["sessions"][0] is None and seen["sessions"][-1] == "sess-1"  # session id sent back after initialize


def _agent_flow(params):
    return {"nodes": [
        {"id": "in", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "ChatInput", "params": {}}},
        {"id": "mcp", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "MCPTools", "params": params, "tool_mode": True}},
        {"id": "agent", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "Agent", "params": {}}},
        {"id": "out", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "ChatOutput", "params": {}}},
    ], "edges": [
        {"id": "1", "source": "in", "sourceHandle": "message", "target": "agent", "targetHandle": "input"},
        {"id": "2", "source": "mcp", "sourceHandle": "tool", "target": "agent", "targetHandle": "tools"},
        {"id": "3", "source": "agent", "sourceHandle": "response", "target": "out", "targetHandle": "input"},
    ]}


def test_agent_uses_mcp_tools(client, stdio_cmd, http_server):
    from tests.test_app import build
    f = client.post("/api/flows", json={"name": "mcp", "data": _agent_flow({"transport": "command", "command": stdio_cmd, "prefix": "t_"})}).json()
    evs = build(client, f["id"], "tool:t_echo:from the agent")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["name"] == "t_echo" and steps[0]["output"] == "echo: from the agent"
    url, _ = http_server
    f = client.post("/api/flows", json={"name": "mcp2", "data": _agent_flow({"transport": "http", "url": url, "only": "weather"})}).json()
    evs = build(client, f["id"], "tool:weather:Porto")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["output"] == "Sunny in Porto"
    # a bad server is a clear error on the node, not a crash
    f = client.post("/api/flows", json={"name": "mcp3", "data": _agent_flow({"transport": "http", "url": "http://127.0.0.1:9/mcp"})}).json()
    evs = build(client, f["id"], "hi")
    assert evs[-1]["event"] == "error" and "Can't reach the MCP server" in evs[-1]["data"]["error"]
