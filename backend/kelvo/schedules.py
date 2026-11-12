"""Scheduled runs: send a fixed message to a flow daily at a time, or every N minutes.

Times are this computer's local time. Results are stored as a chat session
("schedule-<id>"), so they show up in Chat history. Runs are unattended: tools that
need approval (Command Line) don't run.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any

from . import db

TICK_SECONDS = 20
MIN_INTERVAL = 5
_running: set[str] = set()


def now_local() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def compute_next(s: dict[str, Any], after: datetime) -> datetime:
    if s["kind"] == "interval":
        return after + timedelta(minutes=int(s["every_minutes"]))
    hh, mm = (int(x) for x in s["time_of_day"].split(":"))
    days = {int(d) for d in s["days"]}
    cand = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cand <= after:
        cand += timedelta(days=1)
    for _ in range(8):
        if cand.weekday() in days:
            return cand
        cand += timedelta(days=1)
    raise ValueError("Pick at least one day.")


def validate(body: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "name" in body or not partial:
        out["name"] = str(body.get("name") or "Scheduled run").strip()[:80] or "Scheduled run"
    if "message" in body or not partial:
        msg = str(body.get("message") or "").strip()
        if not msg:
            raise ValueError("Write the message the agent should get each time.")
        out["message"] = msg[:4000]
    if "kind" in body or not partial:
        kind = body.get("kind", "daily")
        if kind not in ("daily", "interval"):
            raise ValueError("kind must be daily or interval")
        out["kind"] = kind
    if "time_of_day" in body:
        if body["time_of_day"] is not None and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(body["time_of_day"])):
            raise ValueError("Time must look like 07:30 (24-hour).")
        out["time_of_day"] = body["time_of_day"]
    if "days" in body:
        days = "".join(sorted(set(str(body["days"])) & set("0123456")))
        if not days:
            raise ValueError("Pick at least one day.")
        out["days"] = days
    if "every_minutes" in body:
        if body["every_minutes"] is not None:
            m = int(body["every_minutes"])
            if m < MIN_INTERVAL:
                raise ValueError(f"Every {MIN_INTERVAL} minutes at the most often.")
            out["every_minutes"] = m
    if "enabled" in body:
        out["enabled"] = 1 if body["enabled"] else 0
    return out


def _check_complete(s: dict[str, Any]) -> None:
    if s["kind"] == "daily" and not s.get("time_of_day"):
        raise ValueError("Set the time of day, like 07:30.")
    if s["kind"] == "interval" and not s.get("every_minutes"):
        raise ValueError("Set how many minutes between runs.")


def get(sid: str) -> dict[str, Any] | None:
    with db.conn() as c:
        return db.row(c.execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone())


def list_all(flow_id: str | None = None) -> list[dict[str, Any]]:
    with db.conn() as c:
        q = "SELECT s.*, f.name AS flow_name FROM schedules s JOIN flows f ON f.id = s.flow_id"
        rs = c.execute(q + (" WHERE s.flow_id=?" if flow_id else "") + " ORDER BY s.created_at", (flow_id,) if flow_id else ()).fetchall()
    return db.rows(rs)


def create(flow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    s = {"days": "0123456", "time_of_day": None, "every_minutes": None, "enabled": 1, **validate(body)}
    _check_complete(s)
    sid, t = db.new_id(), db.now()
    nxt = compute_next(s, now_local()).isoformat(timespec="minutes") if s["enabled"] else None
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM flows WHERE id=?", (flow_id,)).fetchone():
            raise LookupError("Flow not found")
        c.execute(
            "INSERT INTO schedules(id,flow_id,name,message,kind,time_of_day,days,every_minutes,enabled,next_run,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, flow_id, s["name"], s["message"], s["kind"], s["time_of_day"], s["days"], s["every_minutes"], s["enabled"], nxt, t, t))
    return get(sid)  # type: ignore[return-value]


def update(sid: str, body: dict[str, Any]) -> dict[str, Any]:
    cur = get(sid)
    if not cur:
        raise LookupError("Schedule not found")
    s = {**cur, **validate(body, partial=True)}
    _check_complete(s)
    nxt = compute_next(s, now_local()).isoformat(timespec="minutes") if s["enabled"] else None
    with db.conn() as c:
        c.execute("UPDATE schedules SET name=?, message=?, kind=?, time_of_day=?, days=?, every_minutes=?, enabled=?, next_run=?, updated_at=? WHERE id=?",
                  (s["name"], s["message"], s["kind"], s["time_of_day"], s["days"], s["every_minutes"], s["enabled"], nxt, db.now(), sid))
    return get(sid)  # type: ignore[return-value]


async def run_schedule(sid: str) -> dict[str, Any]:
    """Run one schedule now (used by the ticker and by 'Run now')."""
    from .engine import Engine, FlowError
    from .main import _run_end, _run_start

    s = get(sid)
    if not s or sid in _running:
        return {"skipped": True}
    _running.add(sid)
    started = now_local()
    try:
        with db.conn() as c:
            flow = db.row(c.execute("SELECT * FROM flows WHERE id=?", (s["flow_id"],)).fetchone(), ("data",))
        engine = Engine(flow, input_value=s["message"], session_id=f"schedule-{sid}", interactive=False)
        rid = _run_start(engine)
        try:
            res = await engine.run()
            texts = [o.get("message", {}).get("text") or o.get("text", "") for o in res["outputs"]]
            status, output = "success", ("\n\n".join(t for t in texts if t) or "(no output)")
            _run_end(rid, engine, None)
        except FlowError as e:
            status, output = "error", str(e)
            _run_end(rid, engine, str(e))
    except Exception as e:  # pragma: no cover - unexpected
        status, output = "error", f"Unexpected error: {e}"
    finally:
        _running.discard(sid)
    s = get(sid)
    if s:
        nxt = compute_next(s, max(started, now_local())).isoformat(timespec="minutes") if s["enabled"] else None
        with db.conn() as c:
            c.execute("UPDATE schedules SET last_run=?, last_status=?, last_output=?, next_run=? WHERE id=?",
                      (started.isoformat(timespec="minutes"), status, output[:4000], nxt, sid))
    return {"status": status, "output": output}


async def tick() -> int:
    """Start every enabled schedule that is due. A schedule missed while the PC was off runs once, then moves on."""
    now = now_local().isoformat(timespec="minutes")
    with db.conn() as c:
        due = [r["id"] for r in c.execute("SELECT id FROM schedules WHERE enabled=1 AND next_run IS NOT NULL AND next_run <= ?", (now,))]
    for sid in due:
        asyncio.create_task(run_schedule(sid))
    return len(due)


async def loop() -> None:
    if os.environ.get("KELVO_SCHEDULER", "1") == "0":
        return
    while True:
        try:
            await tick()
        except Exception as e:  # never let the ticker die
            print(f"Kelvo scheduler: {e}", flush=True)
        await asyncio.sleep(TICK_SECONDS)


__all__ = ["compute_next", "create", "update", "get", "list_all", "run_schedule", "tick", "loop", "json"]
