"""A tiny stand-in for the Ollama API, for tests and demos without a GPU.

Behaviour of /api/chat:
- if tools are offered and the last user message contains "calc:<expr>", it calls the
  first tool whose name contains "calc" with {"expression": expr};
- if a skill is offered (load_skill) and the message contains "skill:<name>", it loads it;
- if the message contains "tool:<name>:<arg>", it calls that tool with {"input": arg} (or the
  first parameter);
- after a tool result, it answers "Result: <tool output>";
- otherwise it echoes "Echo: <last user message>" (streamed word by word).
"""
from __future__ import annotations

import json
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
MODELS = ["llama3.1:8b", "qwen2.5:7b", "gemma2:2b", "nomic-embed-text:latest"]
CAPS = {"llama3.1:8b": ["completion", "tools"], "qwen2.5:7b": ["completion", "tools"],
        "gemma2:2b": ["completion"], "nomic-embed-text:latest": ["embedding"]}
SEEN_AUTH: list[str] = []


@app.post("/api/show")
async def show(req: Request):
    body = await req.json()
    SEEN_AUTH.append(req.headers.get("authorization", ""))
    if body["model"] not in CAPS:
        return JSONResponse({"error": "model not found"}, status_code=404)
    return {"details": {}, "capabilities": CAPS[body["model"]]}


@app.get("/api/tags")
def tags():
    return {"models": [{"name": m, "size": 1, "details": {"family": m.split(":")[0], "parameter_size": "7B"}} for m in MODELS]}


def _vec(text: str) -> list[float]:
    v = [0.0] * 16
    for w in re.findall(r"\w+", text.lower()):
        v[hash(w) % 16] += 1.0
    return v


@app.post("/api/embed")
async def embed(req: Request):
    body = await req.json()
    inp = body["input"] if isinstance(body["input"], list) else [body["input"]]
    return {"model": body["model"], "embeddings": [_vec(t) for t in inp]}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    if "tools" in body and body.get("tools") and "tools" not in CAPS.get(body["model"], ["tools"]):
        return JSONResponse({"error": f"registry.ollama.ai/library/{body['model']} does not support tools"}, status_code=400)
    if body["model"] not in MODELS and body["model"].split(":")[0] not in [m.split(":")[0] for m in MODELS]:
        return JSONResponse({"error": f"model '{body['model']}' not found"}, status_code=404)
    msgs = body["messages"]
    tools = body.get("tools") or []
    last = msgs[-1]
    names = [t["function"]["name"] for t in tools]

    def stream_text(text: str):
        def gen():
            for w in re.split(r"(\s+)", text):
                if w:
                    yield json.dumps({"message": {"role": "assistant", "content": w}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    def call(name: str, args: dict):
        def gen():
            yield json.dumps({"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    if body.get("format") and isinstance(body["format"], dict):
        props = body["format"].get("properties", {})
        out = {k: (re.search(r"[\w.+-]+@[\w.-]+", last["content"]) or [""])[0] if "mail" in k else last["content"].split()[0] if props[k].get("type") == "string" else 0 for k in props}
        return stream_text(json.dumps(out))

    if last["role"] == "tool":
        return stream_text(f"Result: {last['content']}")
    text = last.get("content", "")
    if tools:
        m = re.search(r"skill:([a-z0-9-]+)", text)
        if m and "load_skill" in names:
            return call("load_skill", {"name": m.group(1)})
        m = re.search(r"calc:([^\n]+)", text)
        calc = next((n for n in names if "calc" in n), None)
        if m and calc:
            return call(calc, {"expression": m.group(1).strip()})
        m = re.search(r"tool:([a-z0-9_]+):(.+)", text)
        if m and m.group(1) in names:
            t = next(t for t in tools if t["function"]["name"] == m.group(1))
            props = list(t["function"]["parameters"].get("properties", {}))
            return call(m.group(1), {(props[0] if props else "input"): m.group(2).strip()})
    sys = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
    history = sum(1 for x in msgs if x["role"] in ("user", "assistant")) - 1
    return stream_text(f"Echo: {text}" + (f" [history={history}]" if history else "") + (" [skills]" if "## Skills" in sys else ""))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=11435)
