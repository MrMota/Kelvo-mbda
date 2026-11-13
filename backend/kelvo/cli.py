from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    p = argparse.ArgumentParser(prog="kelvo", description="Visual agent builder powered by Ollama")
    sub = p.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="start the server")
    run.add_argument("--host", default=os.environ.get("KELVO_HOST", "127.0.0.1"))
    run.add_argument("--port", type=int, default=int(os.environ.get("KELVO_PORT", "7860")))
    run.add_argument("--db", help="path to the SQLite database")
    run.add_argument("--reload", action="store_true")
    run.add_argument("--log-file", help="write logs here instead of the console (for running in the background)")
    pw = sub.add_parser("set-password", help="create your account, or reset its username/password")
    pw.add_argument("--db", help="path to the SQLite database")
    dm = sub.add_parser("set-default-model", help="the Ollama model used when an Agent's model is blank")
    dm.add_argument("model")
    dm.add_argument("--db", help="path to the SQLite database")
    bk = sub.add_parser("backup", help="copy the database safely while Kelvo runs")
    bk.add_argument("dest", nargs="?", help="file or folder (default: <db folder>/backups)")
    bk.add_argument("--keep", type=int, default=int(os.environ.get("KELVO_BACKUP_KEEP", "14")), help="backups to keep in the default folder")
    bk.add_argument("--db", help="path to the SQLite database")
    args = p.parse_args()
    if args.cmd == "set-default-model":
        if args.db:
            os.environ["KELVO_DB"] = args.db
        from . import db

        db.init_db()
        db.set_setting("default_model", args.model.strip())
        print(f"Default model: {args.model.strip()}")
        return
    if args.cmd == "backup":
        if args.db:
            os.environ["KELVO_DB"] = args.db
        backup(args.dest, args.keep)
        return
    if args.cmd not in ("run", "set-password"):
        p.print_help()
        return
    if args.db:
        os.environ["KELVO_DB"] = args.db
    if args.cmd == "set-password":
        set_password()
        return
    if args.log_file:
        # Background mode (e.g. pythonw on Windows has no console): send everything to a file.
        from pathlib import Path

        Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
        log = open(args.log_file, "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log
    import uvicorn

    print(f"Kelvo on http://{args.host}:{args.port}  (Ollama: {os.environ.get('OLLAMA_BASE_URL', 'from settings, default http://127.0.0.1:11434')})")
    uvicorn.run("kelvo.main:app", host=args.host, port=args.port, reload=args.reload)


def backup(dest: str | None, keep: int) -> None:
    """SQLite online backup: consistent even while the server is writing (WAL mode)."""
    import sqlite3
    from datetime import datetime
    from pathlib import Path

    from . import db

    src = Path(db.db_path())
    if not src.exists():
        raise SystemExit(f"No database at {src}.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    auto = dest is None
    target = Path(dest) if dest else src.parent / "backups"
    if auto or target.is_dir() or str(dest).endswith("/"):
        target.mkdir(parents=True, exist_ok=True)
        target = target / f"kelvo-{stamp}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(target) as d:
        s.backup(d)
    ok = sqlite3.connect(target).execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        raise SystemExit(f"Backup at {target} failed its integrity check: {ok}")
    print(f"Backup written: {target} ({target.stat().st_size // 1024} KB, integrity ok)")
    if auto and keep > 0:
        old = sorted(target.parent.glob("kelvo-*.db"))[:-keep]
        for f in old:
            f.unlink()
        if old:
            print(f"Removed {len(old)} older backup(s); keeping the newest {keep}.")


def set_password() -> None:
    import getpass

    from fastapi import HTTPException

    from . import auth, db

    db.init_db()
    cur = auth.get_user()
    print(f"Database: {db.db_path()}")
    username = input(f"Username [{cur['username'] if cur else ''}]: ").strip() or (cur["username"] if cur else "")
    p1 = getpass.getpass("New password: ")
    if p1 != getpass.getpass("Repeat it: "):
        raise SystemExit("The passwords don't match. Nothing changed.")
    try:
        auth.set_account(username, p1)
    except HTTPException as e:
        raise SystemExit(str(e.detail))
    print(f"Done. Sign in as '{username}'. Every existing session was signed out.")


if __name__ == "__main__":
    main()
