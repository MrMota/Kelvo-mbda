"""Long-term memory: short facts about you that agents keep across chats."""
from __future__ import annotations

from typing import Any

from . import db

MAX_MEMORIES = 500
IN_PROMPT = 60
MAX_LEN = 500


def all_memories() -> list[dict[str, Any]]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM memories ORDER BY created_at DESC, rowid DESC").fetchall())


def add(text: str) -> dict[str, Any]:
    text = " ".join(str(text).split())[:MAX_LEN]
    if not text:
        raise ValueError("A memory can't be empty.")
    with db.conn() as c:
        same = c.execute("SELECT * FROM memories WHERE lower(text) = lower(?)", (text,)).fetchone()
        if same:
            return dict(same)
        if c.execute("SELECT COUNT(*) FROM memories").fetchone()[0] >= MAX_MEMORIES:
            raise ValueError(f"Memory is full ({MAX_MEMORIES} items). Delete some in Settings → Memory.")
        mid, t = db.new_id(), db.now()
        c.execute("INSERT INTO memories VALUES (?,?,?,?)", (mid, text, t, t))
        return {"id": mid, "text": text, "created_at": t, "updated_at": t}


def update(mid: str, text: str) -> dict[str, Any] | None:
    text = " ".join(str(text).split())[:MAX_LEN]
    if not text:
        raise ValueError("A memory can't be empty.")
    with db.conn() as c:
        c.execute("UPDATE memories SET text=?, updated_at=? WHERE id=?", (text, db.now(), mid))
        return db.row(c.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone())


def delete(mid_or_prefix: str) -> bool:
    key = str(mid_or_prefix).strip().lstrip("m").strip("[]")
    if len(key) < 4:
        return False
    with db.conn() as c:
        rows = c.execute("SELECT id FROM memories WHERE id LIKE ?", (key + "%",)).fetchall()
        if len(rows) != 1:
            return False
        c.execute("DELETE FROM memories WHERE id=?", (rows[0]["id"],))
        return True


def prompt_block() -> str:
    mems = all_memories()[:IN_PROMPT]
    lines = [
        "",
        "## Long-term memory",
        "Facts the user shared in earlier chats (most recent first). Use them when relevant; don't repeat them back unprompted.",
        "When the user tells you a lasting fact or preference (name, setup, projects, how they like answers), call `remember`.",
        "If a memory is wrong or out of date, call `forget` with its id, then `remember` the corrected fact.",
    ]
    lines += [f"- [{m['id'][:8]}] {m['text']}" for m in mems] or ["- (nothing yet)"]
    return "\n".join(lines)
