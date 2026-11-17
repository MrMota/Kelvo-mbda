"""Checkpoints: before an agent writes or edits a file, keep its old content, so you can undo a reply.

Only Files-tool changes are covered; what a command line does can't be undone this way.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import db

MAX_BYTES = 10 * 1024 * 1024
KEEP_DAYS = 30


def save(run_id: str, flow_id: str, session_id: str, path: Path) -> None:
    """Remember how `path` looked before this run first touched it (later writes in the same run are covered)."""
    p = str(path)
    with db.conn() as c:
        if c.execute("SELECT 1 FROM checkpoints WHERE run_id=? AND path=?", (run_id, p)).fetchone():
            return
        existed = path.is_file()
        content, too_big = None, 0
        if existed:
            if path.stat().st_size <= MAX_BYTES:
                content = path.read_bytes()
            else:
                too_big = 1
        c.execute("INSERT INTO checkpoints(id,run_id,flow_id,session_id,path,existed,content,too_big,created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (db.new_id(), run_id, flow_id, session_id, p, int(existed), content, too_big, db.now()))


def changes(run_id: str) -> list[dict[str, Any]]:
    with db.conn() as c:
        rs = c.execute("SELECT path, existed, too_big, restored_at FROM checkpoints WHERE run_id=? ORDER BY created_at, rowid",
                       (run_id,)).fetchall()
    return [{"path": r["path"], "created": not r["existed"], "too_big": bool(r["too_big"]), "restored": bool(r["restored_at"])}
            for r in rs]


def undo(run_id: str) -> dict[str, list[str]]:
    """Put every file this run changed back the way it was (files it created are deleted)."""
    restored, skipped = [], []
    with db.conn() as c:
        rs = c.execute("SELECT * FROM checkpoints WHERE run_id=? AND restored_at IS NULL ORDER BY created_at DESC, rowid DESC",
                       (run_id,)).fetchall()
        for r in rs:
            p = Path(r["path"])
            try:
                if not r["existed"]:
                    if p.is_file():
                        p.unlink()
                elif r["too_big"]:
                    skipped.append(f"{p} (larger than 10 MB, no copy was kept)")
                    continue
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(r["content"])
            except OSError as e:
                skipped.append(f"{p} ({e.strerror or e})")
                continue
            restored.append(str(p))
            c.execute("UPDATE checkpoints SET restored_at=? WHERE id=?", (db.now(), r["id"]))
        # mark the reply in the chat as undone
        c.execute("UPDATE messages SET properties=json_set(properties, '$.changes.undone', json('true')) "
                  "WHERE json_extract(properties, '$.changes.run_id')=?", (run_id,))
    return {"restored": restored, "skipped": skipped}


def prune() -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    with db.conn() as c:
        c.execute("DELETE FROM checkpoints WHERE created_at < ?", (cutoff,))
