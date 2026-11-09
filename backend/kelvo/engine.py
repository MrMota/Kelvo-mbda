"""Graph engine: lazy, pull-based evaluation of a flow.

Terminal nodes (no outgoing edges) are pulled; each node computes an output only
when something downstream asks for it. A node in tool mode turns into a ToolDef
whose call re-runs that node with the agent's arguments as overrides.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Awaitable, Callable

from . import db
from .components import REGISTRY
from .components.base import (
    STOP,
    Component,
    Field,
    Message,
    Stop,
    ToolDef,
    slug,
    to_text,
)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
APPROVAL_TIMEOUT = 300.0
PENDING_APPROVALS: dict[str, "asyncio.Future[bool]"] = {}


def resolve_approval(aid: str, approved: bool) -> bool:
    fut = PENDING_APPROVALS.get(aid)
    if fut is None or fut.done():
        return False
    fut.set_result(bool(approved))
    return True
MAX_DEPTH = 4


class FlowError(Exception):
    def __init__(self, message: str, node_id: str | None = None):
        super().__init__(message)
        self.node_id = node_id


async def _noop(event: str, data: dict[str, Any]) -> None:
    return None


def validate_graph(data: dict[str, Any]) -> list[str]:
    """Return a list of problems (empty = fine)."""
    problems: list[str] = []
    nodes = {n["id"]: n for n in data.get("nodes", []) if n.get("type") != "note"}
    for n in nodes.values():
        key = n.get("data", {}).get("type")
        if key not in REGISTRY:
            problems.append(f"Unknown component '{key}' on node {n['id']}")
    adj: dict[str, list[str]] = {k: [] for k in nodes}
    for e in data.get("edges", []):
        if e["source"] in nodes and e["target"] in nodes:
            adj[e["source"]].append(e["target"])
    state: dict[str, int] = {}

    def visit(u: str) -> bool:
        state[u] = 1
        for v in adj[u]:
            if state.get(v) == 1 or (state.get(v) is None and visit(v)):
                return True
        state[u] = 2
        return False

    if any(state.get(u) is None and visit(u) for u in nodes):
        problems.append("The flow has a cycle; connections must not loop back.")
    return problems


class Engine:
    def __init__(
        self,
        flow: dict[str, Any],
        *,
        input_value: str = "",
        session_id: str | None = None,
        emit: Emit | None = None,
        tweaks: dict[str, Any] | None = None,
        depth: int = 0,
        persist: bool = True,
        interactive: bool = False,
    ):
        self.flow = flow
        self.flow_id: str = flow["id"]
        data = flow["data"] if isinstance(flow["data"], dict) else json.loads(flow["data"])
        self.nodes: dict[str, dict[str, Any]] = {
            n["id"]: n for n in data.get("nodes", []) if n.get("type") != "note"
        }
        self.edges: list[dict[str, Any]] = [
            e for e in data.get("edges", []) if e["source"] in self.nodes and e["target"] in self.nodes
        ]
        self.input_value = input_value
        self.session_id = session_id or self.flow_id
        self.emit = emit or _noop
        self.depth = depth
        self.persist = persist
        self.interactive = interactive  # a person is watching (Playground) and can approve actions
        self.variables = db.variables_map()
        self.memo: dict[tuple[str, str], Any] = {}
        self.locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.instances: dict[str, Component] = {}
        self.stored_message_ids: set[str] = set()
        self.outputs: list[dict[str, Any]] = []  # chat/text outputs for API response
        self.trace: list[dict[str, Any]] = []
        self._apply_tweaks(tweaks or {})
        # nodes whose output goes straight into a Chat Output stream tokens to the UI
        self.streaming_nodes = {
            e["source"] for e in self.edges if self.nodes[e["target"]]["data"]["type"] == "ChatOutput"
        }

    # ------------------------------------------------------------ setup
    def _apply_tweaks(self, tweaks: dict[str, Any]) -> None:
        for target, values in tweaks.items():
            if not isinstance(values, dict):
                continue
            for n in self.nodes.values():
                d = n["data"]
                if target in (n["id"], d.get("type"), d.get("display_name")):
                    d.setdefault("params", {}).update(values)

    def component(self, node_id: str) -> Component:
        if node_id not in self.instances:
            key = self.nodes[node_id]["data"]["type"]
            if key not in REGISTRY:
                raise FlowError(f"Unknown component '{key}'", node_id)
            self.instances[node_id] = REGISTRY[key]()
        return self.instances[node_id]

    def substitute(self, v: Any) -> Any:
        if isinstance(v, str) and "${" in v:
            return VAR_RE.sub(lambda m: self.variables.get(m.group(1), m.group(0)), v)
        return v

    def incoming(self, node_id: str, field: str) -> list[dict[str, Any]]:
        return [e for e in self.edges if e["target"] == node_id and e.get("targetHandle") == field]

    # ------------------------------------------------------------ evaluation
    async def resolve(self, node_id: str, output: str) -> Any:
        key = (node_id, output)
        if key in self.memo:
            return self.memo[key]
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self.memo:
                return self.memo[key]
            node = self.nodes[node_id]
            if output == "tool":
                value = self.make_tool(node_id)
            else:
                value = await self._run_output(node_id, output, overrides={})
            self.memo[key] = value
            return value

    async def _run_output(self, node_id: str, output: str, overrides: dict[str, Any]) -> Any:
        comp = self.component(node_id)
        ctx = NodeCtx(self, node_id, overrides)
        started = time.perf_counter()
        label = self.nodes[node_id]["data"].get("display_name") or comp.display
        await self.emit("node_start", {"node_id": node_id, "output": output, "name": label})
        try:
            value = await comp.compute(ctx, output)
        except SkipBranch:
            value = STOP
        except FlowError:
            raise
        except Exception as e:  # surface which node failed
            await self.emit("node_error", {"node_id": node_id, "error": str(e)})
            raise FlowError(f"{label}: {e}", node_id) from e
        ms = int((time.perf_counter() - started) * 1000)
        preview = "" if isinstance(value, Stop) else _preview(value)
        self.trace.append({"node_id": node_id, "name": label, "output": output, "ms": ms, "skipped": isinstance(value, Stop)})
        await self.emit(
            "node_end",
            {"node_id": node_id, "output": output, "ms": ms, "preview": preview, "skipped": isinstance(value, Stop)},
        )
        return value

    def make_tool(self, node_id: str) -> list[ToolDef]:
        node = self.nodes[node_id]
        d = node["data"]
        comp = self.component(node_id)
        params = d.get("params", {})
        if hasattr(comp, "toolset"):  # e.g. Files: several tools from one component
            return comp.toolset(NodeCtx(self, node_id, {}))
        connected = {e["targetHandle"] for e in self.edges if e["target"] == node_id}
        tparams = [f for f in comp.all_fields(params) if f.tool_param and f.name not in connected]
        props: dict[str, Any] = {}
        required: list[str] = []
        for f in tparams:
            jt = {"int": "integer", "float": "number", "bool": "boolean"}.get(f.type, "string")
            prop: dict[str, Any] = {"type": jt, "description": f.info or f.display}
            if f.options:
                prop["enum"] = f.options
            props[f.name] = prop
            if f.required:
                required.append(f.name)
        out_name = comp.tool_output or next(o.name for o in comp.outputs)
        name = slug(d.get("tool_name") or d.get("display_name") or comp.display)
        desc = d.get("tool_description") or comp.description

        async def call(args: dict[str, Any]) -> str:
            overrides = {k: v for k, v in args.items() if k in props}
            value = await self._run_output(node_id, out_name, overrides)
            return to_text(value)

        return [ToolDef(name=name, description=desc, parameters={"type": "object", "properties": props, "required": required}, fn=call)]

    def terminals(self) -> list[str]:
        sources = {e["source"] for e in self.edges}
        return [nid for nid in self.nodes if nid not in sources]

    async def run(self) -> dict[str, Any]:
        problems = validate_graph({"nodes": list(self.nodes.values()), "edges": self.edges})
        if problems:
            raise FlowError(problems[0])
        if self.depth > MAX_DEPTH:
            raise FlowError("Run Flow nested too deeply.")
        for nid in self.terminals():
            comp = self.component(nid)
            if self.nodes[nid]["data"].get("tool_mode"):
                continue  # a dangling tool does nothing on its own
            for o in comp.outputs[:1]:
                await self.resolve(nid, o.name)
        return {"session_id": self.session_id, "outputs": self.outputs}

    # ------------------------------------------------------------ approvals
    async def ask_approval(self, node_id: str, tool: str, summary: str, details: dict[str, Any]) -> bool:
        """Pause until the person in the Playground approves or rejects (5 min → rejected).
        Runs nobody is watching (API, MCP) are never approved."""
        if not self.interactive:
            return False
        aid = db.new_id()
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        PENDING_APPROVALS[aid] = fut
        await self.emit("approval", {"id": aid, "node_id": node_id, "tool": tool, "summary": summary, "details": details})
        try:
            ok = await asyncio.wait_for(fut, timeout=APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            ok = False
        finally:
            PENDING_APPROVALS.pop(aid, None)
        await self.emit("approval_done", {"id": aid, "approved": ok})
        return ok

    # ------------------------------------------------------------ messages
    def store_message(self, msg: Message) -> Message:
        msg.session_id = msg.session_id or self.session_id
        if not self.persist:
            return msg
        msg.id = db.new_id()
        with db.conn() as c:
            c.execute(
                "INSERT INTO messages(id,flow_id,session_id,sender,sender_name,text,properties,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (msg.id, self.flow_id, msg.session_id, msg.sender, msg.sender_name, msg.text, json.dumps(msg.properties), db.now()),
            )
        self.stored_message_ids.add(msg.id)
        return msg

    def history(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        with db.conn() as c:
            rs = c.execute(
                "SELECT * FROM messages WHERE flow_id=? AND session_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (self.flow_id, session_id, limit + len(self.stored_message_ids)),
            ).fetchall()
        out = [dict(r) for r in rs if r["id"] not in self.stored_message_ids][:limit]
        return list(reversed(out))


class NodeCtx:
    """What a component sees while it runs."""

    def __init__(self, engine: Engine, node_id: str, overrides: dict[str, Any]):
        self.engine = engine
        self.node_id = node_id
        self.overrides = overrides
        self.node = engine.nodes[node_id]
        self.params: dict[str, Any] = self.node["data"].get("params", {})
        self.comp = engine.component(node_id)
        self._fields = {f.name: f for f in self.comp.all_fields(self.params)}

    @property
    def streaming(self) -> bool:
        return self.node_id in self.engine.streaming_nodes

    @property
    def session_id(self) -> str:
        return self.engine.session_id

    def field(self, name: str) -> Field | None:
        return self._fields.get(name)

    def connected(self, name: str) -> bool:
        return bool(self.engine.incoming(self.node_id, name))

    async def get(self, name: str, default: Any = None) -> Any:
        """Field value: tool-call override → connected port(s) → inline param → default."""
        if name in self.overrides:
            return self.overrides[name]
        f = self._fields.get(name)
        edges = self.engine.incoming(self.node_id, name)
        if edges:
            values = [await self.engine.resolve(e["source"], e.get("sourceHandle") or "") for e in edges]
            if f is not None and f.list:
                flat: list[Any] = []
                for v in values:
                    if isinstance(v, Stop):
                        continue
                    flat.extend(v if isinstance(v, list) else [v])
                return flat
            return values[0]
        if name in self.params and self.params[name] not in (None, ""):
            return self.engine.substitute(self.params[name])
        if f is not None and f.default not in (None, ""):
            return f.default
        if f is not None and f.list:
            return []
        return default

    async def text(self, name: str, default: str = "") -> str:
        v = await self.get(name, default)
        if isinstance(v, Stop):
            raise SkipBranch()
        return to_text(v)

    async def emit(self, event: str, data: dict[str, Any]) -> None:
        await self.engine.emit(event, {"node_id": self.node_id, **data})


def _preview(value: Any) -> str:
    if isinstance(value, list) and value and isinstance(value[0], ToolDef):
        return "tools: " + ", ".join(t.name for t in value)
    if hasattr(value, "model") and hasattr(value, "base_url"):
        return f"{value.model} @ {value.base_url}"
    return to_text(value)[:2000]


class SkipBranch(Exception):
    """Raised when a required input comes from an inactive branch."""


def upstream_stop(value: Any) -> bool:
    return isinstance(value, Stop)


__all__ = ["Engine", "FlowError", "NodeCtx", "STOP", "SkipBranch", "validate_graph"]
