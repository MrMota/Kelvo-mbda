"""HTTP API: the editor's REST routes, the run API, MCP and the SPA."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, ollama
from .components import REGISTRY, specs
from .engine import Engine, FlowError, validate_graph
from .templates import STARTER_SKILLS, TEMPLATES

STATIC = Path(os.environ.get("KELVO_STATIC", Path(__file__).parent / "static"))


def seed() -> None:
    db.init_db()
    with db.conn() as c:
        if c.execute("SELECT COUNT(*) FROM settings WHERE key='seeded'").fetchone()[0]:
            return
        t = db.now()
        for s in STARTER_SKILLS:
            c.execute("INSERT OR IGNORE INTO skills VALUES (?,?,?,?,?,?)", (db.new_id(), s["name"], s["description"], s["body"], t, t))
        c.execute("INSERT INTO settings VALUES ('seeded','1')")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    seed()
    yield


app = FastAPI(title="Kelvo", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("KELVO_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

FLOW_JSON = ("data",)


def _flow(c, flow_id: str) -> dict[str, Any]:
    f = db.row(c.execute("SELECT * FROM flows WHERE id=? OR endpoint_name=?", (flow_id, flow_id)).fetchone(), FLOW_JSON)
    if not f:
        raise HTTPException(404, "Flow not found")
    return f


def get_flow(flow_id: str) -> dict[str, Any]:
    with db.conn() as c:
        return _flow(c, flow_id)


def sse(event: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'event': event, 'data': data}, default=str)}\n\n"


# ---------------------------------------------------------------- auth for public APIs

def require_api_key(x_api_key: str | None = Header(None), authorization: str | None = Header(None)) -> None:
    if os.environ.get("KELVO_REQUIRE_API_KEY", "1") == "0":
        return
    key = x_api_key or (authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None)
    if not key:
        raise HTTPException(401, "Missing API key. Send it in the x-api-key header (create one in Settings → API Keys).")
    h = hashlib.sha256(key.encode()).hexdigest()
    with db.conn() as c:
        r = c.execute("SELECT id FROM api_keys WHERE key_hash=?", (h,)).fetchone()
        if not r:
            raise HTTPException(401, "Invalid API key.")
        c.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (db.now(), r["id"]))


# ---------------------------------------------------------------- health, registry, settings

@app.get("/api/health")
async def health() -> dict[str, Any]:
    base = db.ollama_base_url()
    try:
        models = await ollama.list_models(base)
        return {"ok": True, "version": __version__, "ollama": {"url": base, "reachable": True, "models": len(models)}}
    except Exception as e:
        return {"ok": True, "version": __version__, "ollama": {"url": base, "reachable": False, "error": str(e)}}


@app.get("/api/components")
def components() -> dict[str, Any]:
    return specs()


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return {"ollama_base_url": db.ollama_base_url(), "default_model": db.get_setting("default_model", "") or "",
            "default_embed_model": db.get_setting("default_embed_model", "nomic-embed-text")}


@app.put("/api/settings")
def put_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    for k in ("ollama_base_url", "default_model", "default_embed_model"):
        if k in body and body[k] is not None:
            db.set_setting(k, str(body[k]).strip())
    return get_settings()


@app.get("/api/ollama/models")
async def ollama_models(base_url: str | None = None) -> dict[str, Any]:
    base = (base_url or db.ollama_base_url()).rstrip("/")
    try:
        models = await ollama.list_models(base)
    except Exception as e:
        raise HTTPException(502, str(e) if isinstance(e, ollama.OllamaError) else f"Can't reach Ollama at {base}. Start it with `ollama serve`, or fix the URL in Settings → Models.")
    return {"url": base, "models": [
        {"name": m["name"], "size": m.get("size"), "family": (m.get("details") or {}).get("family"),
         "parameter_size": (m.get("details") or {}).get("parameter_size"), "modified_at": m.get("modified_at")}
        for m in models]}


@app.post("/api/ollama/pull")
async def ollama_pull(body: dict[str, Any] = Body(...)) -> StreamingResponse:
    model = str(body.get("model", "")).strip()
    if not model:
        raise HTTPException(422, "model is required")

    async def gen() -> AsyncIterator[str]:
        try:
            async for ev in ollama.pull(db.ollama_base_url(), model):
                yield sse("progress", ev)
            yield sse("end", {"model": model})
        except Exception as e:
            yield sse("error", {"error": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------- projects & flows

@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    with db.conn() as c:
        return db.rows(c.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM flows f WHERE f.project_id=p.id) AS flow_count FROM projects p ORDER BY created_at"
        ).fetchall())


@app.post("/api/projects")
def create_project(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    name = str(body.get("name", "")).strip() or "New Project"
    pid, t = db.new_id(), db.now()
    with db.conn() as c:
        c.execute("INSERT INTO projects VALUES (?,?,?,?)", (pid, name, t, t))
        return db.row(c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())  # type: ignore[return-value]


@app.patch("/api/projects/{pid}")
def rename_project(pid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    with db.conn() as c:
        c.execute("UPDATE projects SET name=?, updated_at=? WHERE id=?", (str(body.get("name", "")).strip() or "Untitled", db.now(), pid))
        r = db.row(c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
    if not r:
        raise HTTPException(404, "Project not found")
    return r


@app.delete("/api/projects/{pid}")
def delete_project(pid: str) -> dict[str, Any]:
    with db.conn() as c:
        if c.execute("SELECT COUNT(*) FROM projects").fetchone()[0] <= 1:
            raise HTTPException(400, "You need at least one project.")
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


def _default_project(c) -> str:
    return c.execute("SELECT id FROM projects ORDER BY created_at LIMIT 1").fetchone()["id"]


def _summary(f: dict[str, Any]) -> dict[str, Any]:
    d = f["data"] if isinstance(f["data"], dict) else json.loads(f["data"])
    types = [n.get("data", {}).get("type") for n in d.get("nodes", []) if n.get("type") != "note"]
    out = {k: v for k, v in f.items() if k != "data"}
    out["node_count"] = len(types)
    out["kind"] = "agent" if "Agent" in types else "flow"
    return out


@app.get("/api/flows")
def list_flows(project_id: str | None = None) -> list[dict[str, Any]]:
    with db.conn() as c:
        if project_id:
            rs = c.execute("SELECT * FROM flows WHERE project_id=? ORDER BY updated_at DESC", (project_id,)).fetchall()
        else:
            rs = c.execute("SELECT * FROM flows ORDER BY updated_at DESC").fetchall()
    return [_summary(f) for f in db.rows(rs, FLOW_JSON)]


@app.get("/api/templates")
def templates() -> list[dict[str, Any]]:
    return [{k: v for k, v in t.items()} for t in TEMPLATES]


@app.post("/api/flows")
def create_flow(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    data: dict[str, Any] = {"nodes": [], "edges": []}
    name = body.get("name")
    desc = body.get("description", "")
    if body.get("template"):
        t = next((t for t in TEMPLATES if t["id"] == body["template"]), None)
        if not t:
            raise HTTPException(404, "Template not found")
        data, name, desc = copy.deepcopy(t["data"]), name or t["name"], desc or t["description"]
    elif body.get("data"):
        data = body["data"]
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
            raise HTTPException(422, "Invalid flow JSON: expected {nodes: [...], edges: [...]}")
    unknown = {n.get("data", {}).get("type") for n in data.get("nodes", []) if n.get("type") != "note"} - set(REGISTRY)
    if unknown:
        raise HTTPException(422, f"Unknown components: {', '.join(sorted(map(str, unknown)))}")
    fid, t = db.new_id(), db.now()
    with db.conn() as c:
        pid = body.get("project_id") or _default_project(c)
        c.execute(
            "INSERT INTO flows(id,project_id,name,description,data,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (fid, pid, (name or "Untitled Flow").strip(), desc, json.dumps(data), t, t),
        )
        return _flow(c, fid)


@app.get("/api/flows/{flow_id}")
def read_flow(flow_id: str) -> dict[str, Any]:
    return get_flow(flow_id)


ENDPOINT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


@app.patch("/api/flows/{flow_id}")
def update_flow(flow_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    with db.conn() as c:
        f = _flow(c, flow_id)
        sets, vals = [], []
        if f["locked"] and "data" in body and body.get("locked") is not False:
            raise HTTPException(423, "This flow is locked. Unlock it in its details to edit.")
        for k in ("name", "description", "project_id", "mcp_tool_name", "mcp_description"):
            if k in body:
                sets.append(f"{k}=?"); vals.append(body[k])
        for k in ("locked", "mcp_enabled"):
            if k in body:
                sets.append(f"{k}=?"); vals.append(1 if body[k] else 0)
        if "endpoint_name" in body:
            ep = (body["endpoint_name"] or "").strip() or None
            if ep and not ENDPOINT_RE.match(ep):
                raise HTTPException(422, "Endpoint name: letters, numbers, - and _ only.")
            if ep and c.execute("SELECT 1 FROM flows WHERE endpoint_name=? AND id<>?", (ep, f["id"])).fetchone():
                raise HTTPException(409, "That endpoint name is taken.")
            sets.append("endpoint_name=?"); vals.append(ep)
        if "data" in body:
            sets.append("data=?"); vals.append(json.dumps(body["data"]))
        if sets:
            sets.append("updated_at=?"); vals.append(db.now())
            c.execute(f"UPDATE flows SET {', '.join(sets)} WHERE id=?", (*vals, f["id"]))
        return _flow(c, f["id"])


@app.delete("/api/flows/{flow_id}")
def delete_flow(flow_id: str) -> dict[str, Any]:
    with db.conn() as c:
        f = _flow(c, flow_id)
        c.execute("DELETE FROM flows WHERE id=?", (f["id"],))
    return {"ok": True}


@app.post("/api/flows/{flow_id}/duplicate")
def duplicate_flow(flow_id: str) -> dict[str, Any]:
    f = get_flow(flow_id)
    return create_flow({"name": f"{f['name']} (copy)", "description": f["description"], "data": f["data"], "project_id": f["project_id"]})


@app.post("/api/flows/{flow_id}/validate")
def validate(flow_id: str, body: dict[str, Any] = Body(None)) -> dict[str, Any]:
    data = (body or {}).get("data") or get_flow(flow_id)["data"]
    return {"problems": validate_graph(data)}


# ---------------------------------------------------------------- running

async def _run_stream(flow: dict[str, Any], input_value: str, session_id: str | None, tweaks: dict[str, Any] | None) -> AsyncIterator[str]:
    q: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await q.put((event, data))

    engine = Engine(flow, input_value=input_value, session_id=session_id, emit=emit, tweaks=tweaks)
    run_id = _run_start(engine)

    async def work() -> None:
        try:
            res = await engine.run()
            _run_end(run_id, engine, None)
            await q.put(("end", res))
        except FlowError as e:
            _run_end(run_id, engine, str(e))
            await q.put(("error", {"error": str(e), "node_id": e.node_id}))
        except Exception as e:  # pragma: no cover - unexpected
            _run_end(run_id, engine, str(e))
            await q.put(("error", {"error": f"Unexpected error: {e}"}))
        finally:
            await q.put(None)

    task = asyncio.create_task(work())
    yield sse("start", {"run_id": run_id, "session_id": engine.session_id})
    try:
        while (item := await q.get()) is not None:
            yield sse(*item)
    finally:
        if not task.done():
            task.cancel()


def _run_start(engine: Engine) -> str:
    rid = db.new_id()
    with db.conn() as c:
        c.execute("INSERT INTO runs(id,flow_id,session_id,status,started_at) VALUES (?,?,?,?,?)",
                  (rid, engine.flow_id, engine.session_id, "running", db.now()))
    return rid


def _run_end(rid: str, engine: Engine, error: str | None) -> None:
    with db.conn() as c:
        c.execute("UPDATE runs SET status=?, error=?, trace=?, finished_at=? WHERE id=?",
                  ("error" if error else "success", error, json.dumps(engine.trace), db.now(), rid))


@app.post("/api/flows/{flow_id}/build")
async def build(flow_id: str, body: dict[str, Any] = Body(...)) -> StreamingResponse:
    """Run from the editor. `data` lets the editor run its unsaved graph."""
    flow = get_flow(flow_id)
    if body.get("data"):
        flow = {**flow, "data": body["data"]}
    return StreamingResponse(
        _run_stream(flow, str(body.get("input_value", "")), body.get("session_id"), body.get("tweaks")),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/run/{flow_id}", dependencies=[Depends(require_api_key)])
async def run_flow(flow_id: str, request: Request, stream: bool = False) -> Any:
    try:
        body = await request.json()
    except Exception:
        body = {}
    flow = get_flow(flow_id)
    input_value = str(body.get("input_value", "") or "")
    session_id = body.get("session_id")
    tweaks = body.get("tweaks")
    if stream or body.get("stream"):
        return StreamingResponse(_run_stream(flow, input_value, session_id, tweaks), media_type="text/event-stream")
    engine = Engine(flow, input_value=input_value, session_id=session_id, tweaks=tweaks)
    rid = _run_start(engine)
    try:
        res = await engine.run()
    except FlowError as e:
        _run_end(rid, engine, str(e))
        raise HTTPException(500, {"error": str(e), "node_id": e.node_id})
    _run_end(rid, engine, None)
    return {
        "session_id": res["session_id"],
        "outputs": [{
            "inputs": {"input_value": input_value},
            "outputs": [
                {"component_id": o["component_id"], "results": {"message": o["message"]} if o["type"] == "chat" else {"text": o["text"]}}
                for o in res["outputs"]
            ],
        }],
    }


# ---------------------------------------------------------------- playground memory & logs

@app.get("/api/flows/{flow_id}/sessions")
def sessions(flow_id: str) -> list[dict[str, Any]]:
    with db.conn() as c:
        return db.rows(c.execute(
            "SELECT session_id, COUNT(*) AS count, MAX(created_at) AS last, "
            "(SELECT text FROM messages m2 WHERE m2.flow_id=m.flow_id AND m2.session_id=m.session_id AND sender='user' ORDER BY created_at, rowid LIMIT 1) AS title "
            "FROM messages m WHERE flow_id=? GROUP BY session_id ORDER BY last DESC", (flow_id,)).fetchall())


@app.get("/api/flows/{flow_id}/messages")
def messages(flow_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
    with db.conn() as c:
        if session_id:
            rs = c.execute("SELECT * FROM messages WHERE flow_id=? AND session_id=? ORDER BY created_at, rowid", (flow_id, session_id))
        else:
            rs = c.execute("SELECT * FROM messages WHERE flow_id=? ORDER BY created_at, rowid", (flow_id,))
        return db.rows(rs.fetchall(), ("properties",))


@app.delete("/api/flows/{flow_id}/messages")
def delete_session(flow_id: str, session_id: str) -> dict[str, Any]:
    with db.conn() as c:
        n = c.execute("DELETE FROM messages WHERE flow_id=? AND session_id=?", (flow_id, session_id)).rowcount
    return {"deleted": n}


@app.patch("/api/messages/{mid}")
def edit_message(mid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    with db.conn() as c:
        c.execute("UPDATE messages SET text=? WHERE id=?", (str(body.get("text", "")), mid))
        r = db.row(c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone(), ("properties",))
    if not r:
        raise HTTPException(404, "Message not found")
    return r


@app.delete("/api/messages/{mid}")
def delete_message(mid: str) -> dict[str, Any]:
    with db.conn() as c:
        c.execute("DELETE FROM messages WHERE id=?", (mid,))
    return {"ok": True}


@app.get("/api/flows/{flow_id}/runs")
def runs(flow_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM runs WHERE flow_id=? ORDER BY started_at DESC, rowid DESC LIMIT ?",
                                 (flow_id, limit)).fetchall(), ("trace",))


# ---------------------------------------------------------------- skills

SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _skill_body(body: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "name" in body or not partial:
        name = str(body.get("name", "")).strip().lower()
        if not SKILL_NAME.match(name):
            raise HTTPException(422, "Skill name: lowercase letters, numbers and dashes, up to 64 characters.")
        out["name"] = name
    if "description" in body or not partial:
        desc = str(body.get("description", "")).strip()
        if not desc:
            raise HTTPException(422, "Describe when the agent should use this skill.")
        if len(desc) > 1024:
            raise HTTPException(422, "Description: 1024 characters at most.")
        out["description"] = desc
    if "body" in body or not partial:
        out["body"] = str(body.get("body", ""))
    return out


@app.get("/api/skills")
def list_skills() -> list[dict[str, Any]]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM skills ORDER BY name").fetchall())


@app.post("/api/skills")
def create_skill(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    s = _skill_body(body)
    sid, t = db.new_id(), db.now()
    with db.conn() as c:
        if c.execute("SELECT 1 FROM skills WHERE name=?", (s["name"],)).fetchone():
            raise HTTPException(409, f"A skill named '{s['name']}' already exists.")
        c.execute("INSERT INTO skills VALUES (?,?,?,?,?,?)", (sid, s["name"], s["description"], s["body"], t, t))
        return db.row(c.execute("SELECT * FROM skills WHERE id=?", (sid,)).fetchone())  # type: ignore[return-value]


@app.get("/api/skills/{sid}")
def read_skill(sid: str) -> dict[str, Any]:
    with db.conn() as c:
        r = db.row(c.execute("SELECT * FROM skills WHERE id=? OR name=?", (sid, sid)).fetchone())
    if not r:
        raise HTTPException(404, "Skill not found")
    return r


@app.patch("/api/skills/{sid}")
def update_skill(sid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    cur = read_skill(sid)
    s = _skill_body(body, partial=True)
    with db.conn() as c:
        if "name" in s and c.execute("SELECT 1 FROM skills WHERE name=? AND id<>?", (s["name"], cur["id"])).fetchone():
            raise HTTPException(409, f"A skill named '{s['name']}' already exists.")
        if s:
            sets = ", ".join(f"{k}=?" for k in s)
            c.execute(f"UPDATE skills SET {sets}, updated_at=? WHERE id=?", (*s.values(), db.now(), cur["id"]))
    return read_skill(cur["id"])


@app.delete("/api/skills/{sid}")
def delete_skill(sid: str) -> dict[str, Any]:
    cur = read_skill(sid)
    with db.conn() as c:
        c.execute("DELETE FROM skills WHERE id=?", (cur["id"],))
    return {"ok": True}


def parse_skill_md(text: str) -> dict[str, Any]:
    """SKILL.md: YAML-ish front matter (name, description) + markdown body."""
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        raise HTTPException(422, "SKILL.md must start with front matter: ---, name:, description:, ---")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return {"name": meta.get("name", ""), "description": meta.get("description", ""), "body": m.group(2).strip()}


def to_skill_md(s: dict[str, Any]) -> str:
    desc = s["description"].replace("\n", " ")
    return f"---\nname: {s['name']}\ndescription: {desc}\n---\n\n{s['body'].strip()}\n"


@app.post("/api/skills/import")
def import_skill(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    parsed = parse_skill_md(str(body.get("content", "")))
    if body.get("overwrite"):
        with db.conn() as c:
            r = c.execute("SELECT id FROM skills WHERE name=?", (parsed["name"],)).fetchone()
        if r:
            return update_skill(r["id"], parsed)
    return create_skill(parsed)


@app.get("/api/skills/{sid}/export")
def export_skill(sid: str) -> PlainTextResponse:
    s = read_skill(sid)
    return PlainTextResponse(to_skill_md(s), headers={"Content-Disposition": f'attachment; filename="{s["name"]}.SKILL.md"'})


# ---------------------------------------------------------------- global variables

def _mask(v: dict[str, Any]) -> dict[str, Any]:
    if v["type"] == "credential":
        v = {**v, "value": "••••••••"}
    return v


@app.get("/api/variables")
def list_variables() -> list[dict[str, Any]]:
    with db.conn() as c:
        return [_mask(v) for v in db.rows(c.execute("SELECT * FROM variables ORDER BY name").fetchall())]


VAR_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


@app.post("/api/variables")
def create_variable(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    name, typ = str(body.get("name", "")).strip(), body.get("type", "generic")
    if not VAR_NAME.match(name):
        raise HTTPException(422, "Variable name: letters, numbers and _ only, not starting with a number.")
    if typ not in ("generic", "credential"):
        raise HTTPException(422, "type must be generic or credential")
    vid, t = db.new_id(), db.now()
    with db.conn() as c:
        if c.execute("SELECT 1 FROM variables WHERE name=?", (name,)).fetchone():
            raise HTTPException(409, f"A variable named {name} already exists.")
        c.execute("INSERT INTO variables VALUES (?,?,?,?,?,?)", (vid, name, typ, str(body.get("value", "")), t, t))
        return _mask(db.row(c.execute("SELECT * FROM variables WHERE id=?", (vid,)).fetchone()))  # type: ignore[arg-type]


@app.patch("/api/variables/{vid}")
def update_variable(vid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    with db.conn() as c:
        cur = db.row(c.execute("SELECT * FROM variables WHERE id=?", (vid,)).fetchone())
        if not cur:
            raise HTTPException(404, "Variable not found")
        name = str(body.get("name", cur["name"])).strip()
        if not VAR_NAME.match(name):
            raise HTTPException(422, "Variable name: letters, numbers and _ only.")
        value = body.get("value", cur["value"])
        if value == "••••••••":
            value = cur["value"]
        c.execute("UPDATE variables SET name=?, value=?, updated_at=? WHERE id=?", (name, str(value), db.now(), vid))
        return _mask(db.row(c.execute("SELECT * FROM variables WHERE id=?", (vid,)).fetchone()))  # type: ignore[arg-type]


@app.delete("/api/variables/{vid}")
def delete_variable(vid: str) -> dict[str, Any]:
    with db.conn() as c:
        c.execute("DELETE FROM variables WHERE id=?", (vid,))
    return {"ok": True}


# ---------------------------------------------------------------- API keys

@app.get("/api/api-keys")
def list_keys() -> list[dict[str, Any]]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT id, name, prefix, created_at, last_used_at FROM api_keys ORDER BY created_at DESC").fetchall())


@app.post("/api/api-keys")
def create_key(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    key = "kelvo-" + secrets.token_urlsafe(32)
    kid = db.new_id()
    with db.conn() as c:
        c.execute("INSERT INTO api_keys(id,name,key_hash,prefix,created_at) VALUES (?,?,?,?,?)",
                  (kid, str(body.get("name", "")).strip() or "API key", hashlib.sha256(key.encode()).hexdigest(), key[:10], db.now()))
    return {"id": kid, "key": key, "prefix": key[:10]}


@app.delete("/api/api-keys/{kid}")
def delete_key(kid: str) -> dict[str, Any]:
    with db.conn() as c:
        c.execute("DELETE FROM api_keys WHERE id=?", (kid,))
    return {"ok": True}


# ---------------------------------------------------------------- MCP server

from .mcp import router as mcp_router  # noqa: E402

app.include_router(mcp_router)


# ---------------------------------------------------------------- SPA

if STATIC.is_dir() and (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith(("api/", "mcp")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        f = STATIC / path
        if path and f.is_file() and STATIC in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
