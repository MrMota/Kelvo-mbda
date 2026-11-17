"""Compaction: summarize the older part of a chat so a small model's context window doesn't overflow.

A summary is saved as a chat message (sender_name "Summary", properties.summary = true) right after the
last message it covers. When an agent loads chat memory, it starts from the newest summary.
"""
from __future__ import annotations

import json
from typing import Any

from . import db, ollama

SUMMARY_SYSTEM = (
    "You compress conversations so an assistant can continue them without the full text. Write a concise summary "
    "(under 250 words) that keeps: the user's goals and preferences, decisions made, file paths, commands and their "
    "results, facts found, and anything still to do. Plain text, no preamble.")
MAX_CHARS = 60_000


def _transcript(items: list[dict[str, Any]]) -> str:
    parts = []
    for m in items:
        role = m.get("role") or ("user" if m.get("sender") == "user" else "assistant")
        text = str(m.get("content") if "content" in m else m.get("text") or "")
        if m.get("tool_calls"):
            text += "\n[called tools: " + ", ".join((c.get("function") or {}).get("name", "?") for c in m["tool_calls"]) + "]"
        if role == "tool":
            role = f"tool result ({m.get('tool_name', '')})"
        parts.append(f"{role}: {text[:4000]}")
    out = "\n\n".join(parts)
    return out[-MAX_CHARS:]


async def summarize(base_url: str, model: str, items: list[dict[str, Any]], options: dict[str, Any] | None = None) -> str:
    r = await ollama.chat(base_url, model, [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": "Summarize this conversation:\n\n" + _transcript(items)},
    ], options=options or None)
    return r["content"].strip() or "(no summary)"


def store_summary(flow_id: str, session_id: str, text: str, covers_until: str, covered: int) -> dict[str, Any]:
    """Save the summary right after the last message it covers (same timestamp, later row)."""
    mid = db.new_id()
    props = {"summary": True, "covered": covered}
    with db.conn() as c:
        c.execute("INSERT INTO messages(id,flow_id,session_id,sender,sender_name,text,properties,created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (mid, flow_id, session_id, "machine", "Summary", text, json.dumps(props), covers_until))
        return db.row(c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone(), ("properties",)) or {}


def _flow_model(flow: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    data = flow["data"] if isinstance(flow["data"], dict) else json.loads(flow["data"])
    for n in data.get("nodes", []):
        d = n.get("data") or {}
        if d.get("type") == "Agent":
            p = d.get("params") or {}
            opts = {"num_ctx": int(p["num_ctx"])} if p.get("num_ctx") else {}
            return (p.get("base_url") or db.ollama_base_url()).rstrip("/"), p.get("model") or db.get_setting("default_model") or "", opts
    return db.ollama_base_url().rstrip("/"), db.get_setting("default_model") or "", {}


async def compact_session(flow: dict[str, Any], session_id: str, keep: int = 2) -> dict[str, Any]:
    """The Compact button: summarize everything since the last summary except the last `keep` messages."""
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT * FROM messages WHERE flow_id=? AND session_id=? ORDER BY created_at, rowid",
                               (flow["id"], session_id)).fetchall(), ("properties",))
    last = max((i for i, m in enumerate(rs) if (m.get("properties") or {}).get("summary")), default=-1)
    items = rs[last:] if last >= 0 else rs  # the previous summary is part of what gets summarized
    items = items[:-keep] if keep else items
    if len([m for m in items if not (m.get("properties") or {}).get("summary")]) < 3:
        raise ValueError("Nothing to compact yet: this chat is still short.")
    base, model, opts = _flow_model(flow)
    if not model:
        raise ValueError("Pick a model on the Agent, or set a default in Settings → Models.")
    text = await summarize(base, model, items, opts)
    return store_summary(flow["id"], session_id, text, items[-1]["created_at"], len(items))
