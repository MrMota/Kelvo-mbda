import json

from kelvo.components.tools import safe_eval
from kelvo.components.base import prompt_vars, fill_prompt
from kelvo.components.logic import split_text


def events(resp):
    out = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def build(client, flow_id, text, session="s1", data=None):
    r = client.post(f"/api/flows/{flow_id}/build", json={"input_value": text, "session_id": session, "data": data})
    assert r.status_code == 200
    return events(r)


def final_messages(evs):
    return [e["data"]["message"]["text"] for e in evs if e["event"] == "message"]


# ---------------------------------------------------------------- units

def test_safe_eval():
    assert safe_eval("(4 + 4) * 2") == 16
    assert safe_eval("sqrt(16) + 2^3") == 12
    try:
        safe_eval("__import__('os')")
        assert False
    except ValueError:
        pass


def test_prompt_vars():
    assert prompt_vars("Hi {name}, {{literal}} {name} {topic}") == ["name", "topic"]
    assert fill_prompt("Hi {name} {{x}}", {"name": "Ana"}) == "Hi Ana {x}"


def test_split_text():
    chunks = split_text("word " * 500, 200, 50)
    assert len(chunks) > 5 and all(len(c) <= 200 for c in chunks)


# ---------------------------------------------------------------- api

def test_health_and_components(client):
    h = client.get("/api/health").json()
    assert h["ollama"]["reachable"] is True
    spec = client.get("/api/components").json()
    keys = {c["key"] for c in spec["components"]}
    assert {"Agent", "Skill", "OllamaModel", "ChatInput", "ChatOutput", "KnowledgeBase"} <= keys
    assert client.get("/api/ollama/models").json()["models"][0]["name"] == "llama3.1:8b"


def test_basic_prompting_template(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    evs = build(client, f["id"], "What is Ollama?")
    assert any(e["event"] == "token" for e in evs), "tokens should stream to the chat"
    [msg] = final_messages(evs)
    assert msg.startswith("Echo: You are a friendly expert") and "Question: What is Ollama?" in msg
    assert evs[-1]["event"] == "end"


def test_agent_calls_tool_and_shows_step(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    evs = build(client, f["id"], "calc: (4+4)*2")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps and steps[0]["name"] == "calculator"
    assert '"result": 16' in steps[0]["output"]
    [msg] = final_messages(evs)
    assert msg.startswith("Result:")
    stored = client.get(f"/api/flows/{f['id']}/messages", params={"session_id": "s1"}).json()
    assert [m["sender"] for m in stored] == ["user", "machine"]
    assert stored[1]["properties"]["steps"][0]["name"] == "calculator"


def test_agent_memory(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    build(client, f["id"], "hello", session="mem")
    [msg] = final_messages(build(client, f["id"], "again", session="mem"))
    assert "[history=2]" in msg  # previous user + assistant, not the current message twice
    sessions = client.get(f"/api/flows/{f['id']}/sessions").json()
    assert sessions[0]["session_id"] == "mem" and sessions[0]["count"] == 4


def test_skills_progressive_loading(client):
    f = client.post("/api/flows", json={"template": "skilled-agent"}).json()
    evs = build(client, f["id"], "please use skill:email-writer")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["name"] == "load_skill"
    assert "Skill: email-writer" in steps[0]["output"]
    # library skills are also loadable (template uses "*")
    evs = build(client, f["id"], "skill:summarize", session="s2")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert "# Summarize" in steps[0]["output"]
    # without a skill request the agent only sees the list
    [msg] = final_messages(build(client, f["id"], "hi", session="s3"))
    assert "[skills]" in msg


def test_multi_agent(client):
    f = client.post("/api/flows", json={"template": "multi-agent"}).json()
    evs = build(client, f["id"], "tool:researcher:find the capital of France")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["name"] == "researcher"
    assert steps[0]["output"].startswith("Echo: find the capital of France")


def test_rag_template(client):
    f = client.post("/api/flows", json={"template": "document-qa"}).json()
    evs = build(client, f["id"], "Where are vectors kept?")
    [msg] = final_messages(evs)
    assert "Context:" in msg and "database" in msg
    # ingest is idempotent
    build(client, f["id"], "again")
    from kelvo import db
    with db.conn() as c:
        assert c.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0] == 1


def test_structured_output(client):
    f = client.post("/api/flows", json={"template": "structured-extraction"}).json()
    [msg] = final_messages(build(client, f["id"], "Ana at ana@example.com from Acme"))
    assert "Email: ana@example.com" in msg


def test_if_else_branch(client):
    data = {"nodes": [
        {"id": "in", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "ChatInput", "params": {}}},
        {"id": "if", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "IfElse", "params": {"operator": "contains", "match": "urgent"}}},
        {"id": "yes", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "ChatOutput", "params": {"sender_name": "Urgent"}}},
        {"id": "no", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "ChatOutput", "params": {"sender_name": "Normal"}}},
    ], "edges": [
        {"id": "1", "source": "in", "sourceHandle": "message", "target": "if", "targetHandle": "input"},
        {"id": "2", "source": "if", "sourceHandle": "true", "target": "yes", "targetHandle": "input"},
        {"id": "3", "source": "if", "sourceHandle": "false", "target": "no", "targetHandle": "input"},
    ]}
    f = client.post("/api/flows", json={"name": "router", "data": data}).json()
    evs = build(client, f["id"], "this is URGENT")
    names = [e["data"]["message"]["sender_name"] for e in evs if e["event"] == "message"]
    assert names == ["Urgent"]


def test_cycle_rejected(client):
    data = {"nodes": [
        {"id": "a", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "Parser", "params": {}}},
        {"id": "b", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "Parser", "params": {}}},
    ], "edges": [
        {"id": "1", "source": "a", "sourceHandle": "text", "target": "b", "targetHandle": "input"},
        {"id": "2", "source": "b", "sourceHandle": "text", "target": "a", "targetHandle": "input"},
    ]}
    f = client.post("/api/flows", json={"name": "loop", "data": data}).json()
    evs = build(client, f["id"], "x")
    assert evs[-1]["event"] == "error" and "cycle" in evs[-1]["data"]["error"]


def test_missing_model_error(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    data = f["data"]
    for n in data["nodes"]:
        if n["data"]["type"] == "OllamaModel":
            n["data"]["params"]["model"] = "nonexistent:1b"
    evs = build(client, f["id"], "hi", data=data)
    assert evs[-1]["event"] == "error" and "Pull it in Settings" in evs[-1]["data"]["error"]
    runs = client.get(f"/api/flows/{f['id']}/runs").json()
    assert runs[0]["status"] == "error"


def test_run_api_with_key_and_tweaks(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    assert client.post(f"/api/v1/run/{f['id']}", json={"input_value": "hi"}).status_code == 401
    key = client.post("/api/api-keys", json={"name": "test"}).json()["key"]
    r = client.post(f"/api/v1/run/{f['id']}", headers={"x-api-key": key},
                    json={"input_value": "hi", "session_id": "api-1", "tweaks": {"prompt": {"template": "Say {question}"}}})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["session_id"] == "api-1"
    assert out["outputs"][0]["outputs"][0]["results"]["message"]["text"] == "Echo: Say hi"
    # endpoint alias
    client.patch(f"/api/flows/{f['id']}", json={"endpoint_name": "hello-bot"})
    r = client.post("/api/v1/run/hello-bot", headers={"Authorization": f"Bearer {key}"}, json={"input_value": "yo"})
    assert r.json()["outputs"][0]["outputs"][0]["results"]["message"]["text"].endswith("Question: yo")
    # streaming
    r = client.post(f"/api/v1/run/{f['id']}?stream=true", headers={"x-api-key": key}, json={"input_value": "s"})
    assert any(e["event"] == "token" for e in events(r))


def test_mcp_server(client):
    key = client.post("/api/api-keys", json={"name": "mcp"}).json()["key"]
    h = {"x-api-key": key}
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    client.patch(f"/api/flows/{f['id']}", json={"mcp_enabled": True, "mcp_tool_name": "ask_expert", "mcp_description": "Ask an expert"})
    init = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).json()
    assert init["result"]["serverInfo"]["name"] == "kelvo"
    assert client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    tools = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()
    assert tools["result"]["tools"][0]["name"] == "ask_expert"
    res = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                "params": {"name": "ask_expert", "arguments": {"input_value": "why?"}}}).json()
    assert "Question: why?" in res["result"]["content"][0]["text"]


def test_skills_crud_import_export(client):
    assert {s["name"] for s in client.get("/api/skills").json()} >= {"summarize", "code-review"}
    s = client.post("/api/skills", json={"name": "haiku", "description": "Use for poems", "body": "5-7-5"}).json()
    assert client.post("/api/skills", json={"name": "haiku", "description": "x"}).status_code == 409
    assert client.post("/api/skills", json={"name": "Bad Name", "description": "x"}).status_code == 422
    md = client.get(f"/api/skills/{s['id']}/export").text
    assert md.startswith("---\nname: haiku\n")
    client.delete(f"/api/skills/{s['id']}")
    s2 = client.post("/api/skills/import", json={"content": md}).json()
    assert s2["name"] == "haiku" and s2["body"] == "5-7-5"


def test_variables_masked_and_substituted(client):
    v = client.post("/api/variables", json={"name": "PERSONA", "type": "credential", "value": "a pirate"}).json()
    assert v["value"] == "••••••••"
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    data = f["data"]
    for n in data["nodes"]:
        if n["data"]["type"] == "Prompt":
            n["data"]["params"]["template"] = "Talk like ${PERSONA}: {question}"
    [msg] = final_messages(build(client, f["id"], "hi", data=data))
    assert msg == "Echo: Talk like a pirate: hi"


def test_flow_crud(client):
    f = client.post("/api/flows", json={"name": "Mine"}).json()
    d = client.post(f"/api/flows/{f['id']}/duplicate").json()
    assert d["name"] == "Mine (copy)"
    assert len(client.get("/api/flows").json()) == 2
    client.patch(f"/api/flows/{f['id']}", json={"locked": True})
    assert client.patch(f"/api/flows/{f['id']}", json={"data": {"nodes": [], "edges": []}}).status_code == 423
    assert client.post("/api/flows", json={"data": {"nodes": [{"id": "x", "data": {"type": "Nope"}}], "edges": []}}).status_code == 422
    client.delete(f"/api/flows/{d['id']}")
    assert len(client.get("/api/flows").json()) == 1


def test_model_capabilities_and_api_key(client):
    from kelvo.fake_ollama import SEEN_AUTH
    models = {m["name"]: m["capabilities"] for m in client.get("/api/ollama/models").json()["models"]}
    assert models["llama3.1:8b"] == ["completion", "tools"] and models["gemma2:2b"] == ["completion"]
    # API key: write-only, sent as a Bearer token
    client.put("/api/settings", json={"ollama_api_key": "sk-test"})
    s = client.get("/api/settings").json()
    assert s["has_ollama_api_key"] is True and "sk-test" not in str(s)
    from kelvo import ollama
    ollama._caps_cache.clear()
    client.get("/api/ollama/models")
    assert SEEN_AUTH[-1] == "Bearer sk-test"


def test_agent_on_model_without_tools_explains(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    data = f["data"]
    for n in data["nodes"]:
        if n["data"].get("type") == "Agent":
            n["data"]["params"]["model"] = "gemma2:2b"
    evs = build(client, f["id"], "hi", data=data)
    assert evs[-1]["event"] == "error" and "can't call tools" in evs[-1]["data"]["error"]


def test_startup_makes_no_network_calls(tmp_path, monkeypatch):
    """X1: booting Kelvo must not touch the network (air-gapped servers start instantly)."""
    import socket

    calls = []
    real = socket.socket.connect

    def spy(self, addr):
        calls.append(addr)
        return real(self, addr)

    monkeypatch.setattr(socket.socket, "connect", spy)
    monkeypatch.setenv("KELVO_DB", str(tmp_path / "boot.db"))
    from fastapi.testclient import TestClient

    from kelvo.main import app

    with TestClient(app):
        pass
    assert calls == []


def test_startup_time_budget(tmp_path):
    """X1: a cold start (fresh database) answers in under 3 s."""
    import os, socket, subprocess, sys, time, urllib.request

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "KELVO_DB": str(tmp_path / "cold.db")}
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, "-m", "kelvo.cli", "run", "--port", str(port)], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while True:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auth/status", timeout=0.5)
                break
            except OSError:
                if time.perf_counter() - t0 > 10:
                    raise AssertionError("did not start within 10 s")
                time.sleep(0.05)
        assert time.perf_counter() - t0 < 3.0
    finally:
        p.terminate()
        p.wait(5)
