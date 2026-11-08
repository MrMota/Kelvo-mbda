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
    args = p.parse_args()
    if args.cmd != "run":
        p.print_help()
        return
    if args.db:
        os.environ["KELVO_DB"] = args.db
    import uvicorn

    print(f"Kelvo on http://{args.host}:{args.port}  (Ollama: {os.environ.get('OLLAMA_BASE_URL', 'from settings, default http://127.0.0.1:11434')})")
    uvicorn.run("kelvo.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
