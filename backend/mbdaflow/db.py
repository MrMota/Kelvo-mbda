"""SQLite access. One connection per call; WAL mode; raw SQL."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def db_path() -> str:
    return os.environ.get("MBDAFLOW_DB", str(Path.home() / ".mbdaflow" / "mbdaflow.db"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    path = db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
            t = now()
            c.execute("INSERT INTO projects VALUES (?,?,?,?)", (new_id(), "My Projects", t, t))


def row(r: sqlite3.Row | None, json_fields: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for f in json_fields:
        if f in d and isinstance(d[f], str):
            d[f] = json.loads(d[f])
    return d


def rows(rs: list[sqlite3.Row], json_fields: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    return [row(r, json_fields) for r in rs]  # type: ignore[misc]


def get_setting(key: str, default: str | None = None) -> str | None:
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def ollama_base_url() -> str:
    return (
        get_setting("ollama_base_url")
        or os.environ.get("OLLAMA_HOST_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def variables_map() -> dict[str, str]:
    with conn() as c:
        return {r["name"]: r["value"] for r in c.execute("SELECT name, value FROM variables")}
