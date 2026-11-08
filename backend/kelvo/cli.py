from __future__ import annotations

import argparse
import os


def main() -> None:
    p = argparse.ArgumentParser(prog="kelvo", description="Visual agent builder powered by Ollama")
    sub = p.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="start the server")
    run.add_argument("--host", default=os.environ.get("KELVO_HOST", "127.0.0.1"))
    run.add_argument("--port", type=int, default=int(os.environ.get("KELVO_PORT", "7860")))
    run.add_argument("--db", help="path to the SQLite database")
    run.add_argument("--reload", action="store_true")
    pw = sub.add_parser("set-password", help="create your account, or reset its username/password")
    pw.add_argument("--db", help="path to the SQLite database")
    args = p.parse_args()
    if args.cmd not in ("run", "set-password"):
        p.print_help()
        return
    if args.db:
        os.environ["KELVO_DB"] = args.db
    if args.cmd == "set-password":
        set_password()
        return
    import uvicorn

    print(f"Kelvo on http://{args.host}:{args.port}  (Ollama: {os.environ.get('OLLAMA_BASE_URL', 'from settings, default http://127.0.0.1:11434')})")
    uvicorn.run("kelvo.main:app", host=args.host, port=args.port, reload=args.reload)


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
