import asyncio
import json
import time

from kelvo import main
from kelvo.engine import resolve_approval


def _events(chunks):
    return [json.loads(l[6:]) for l in "".join(chunks).splitlines() if l.startswith("data: ")]


def test_run_survives_disconnect(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    with client.stream("POST", f"/api/flows/{f['id']}/build", json={"input_value": "slow:2 still here?", "session_id": "phone"}) as r:
        first = next(r.iter_lines())  # the phone locks right after the run starts
        assert '"start"' in first
    st = client.get(f"/api/flows/{f['id']}/status", params={"session_id": "phone"}).json()
    assert st["running"] is True and st["run_id"]
    deadline = time.time() + 15
    while client.get(f"/api/flows/{f['id']}/status", params={"session_id": "phone"}).json()["running"]:
        assert time.time() < deadline, "run never finished"
        time.sleep(0.2)
    msgs = client.get(f"/api/flows/{f['id']}/messages", params={"session_id": "phone"}).json()
    assert msgs[-1]["sender"] == "machine" and "still here?" in msgs[-1]["text"]
    run = client.get(f"/api/flows/{f['id']}/runs").json()[0]
    assert run["status"] == "success"


def test_stop_button_cancels_and_logs_it(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    flow = main.get_flow(f["id"])

    async def go():
        evs = []
        gen = main._run_stream(flow, "slow:5 never mind", "stopme", None, interactive=True)
        async for chunk in gen:
            if chunk.startswith("data: "):
                e = json.loads(chunk[6:])
                evs.append(e)
                if e["event"] == "start":
                    await asyncio.sleep(0.3)
                    assert main.cancel_run(e["data"]["run_id"])["ok"]
        return evs
    evs = asyncio.run(go())
    assert evs[-1] == {"event": "error", "data": {"error": "Stopped."}}
    run = client.get(f"/api/flows/{f['id']}/runs").json()[0]
    assert run["status"] == "error" and run["error"] == "Stopped by you." and run["finished_at"]
    assert main.cancel_run("not-running")["ok"] is False


def test_keepalive_during_quiet_runs(client, monkeypatch):
    monkeypatch.setattr(main, "KEEPALIVE_SECONDS", 0.2)
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    r = client.post(f"/api/flows/{f['id']}/build", json={"input_value": "slow:1 hi", "session_id": "ka"})
    assert ": keep-alive" in r.text and '"event": "end"' in r.text


def test_status_reports_waiting_approvals(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    flow = {"id": "f-appr", "name": "x", "data": {"nodes": [
        {"id": "sh", "type": "component", "position": {"x": 0, "y": 0}, "data": {"type": "Shell", "params": {"command": "echo ok"}}}], "edges": []}}
    from kelvo import db
    with db.conn() as c:
        pid = c.execute("SELECT id FROM projects LIMIT 1").fetchone()["id"]
        c.execute("INSERT INTO flows(id,project_id,name,description,data,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                  ("f-appr", pid, "x", "", json.dumps(flow["data"]), db.now(), db.now()))
    seen = {}

    async def go():
        async for chunk in main._run_stream(main.get_flow("f-appr"), "", "sess-a", None, interactive=True):
            if not chunk.startswith("data: "):
                continue
            e = json.loads(chunk[6:])
            if e["event"] == "approval":
                seen["status"] = main.chat_status("f-appr", "sess-a")
                resolve_approval(e["data"]["id"], True)
    asyncio.run(go())
    st = seen["status"]
    assert st["running"] and st["approvals"][0]["summary"] == "echo ok" and "session_id" not in st["approvals"][0]
    assert main.chat_status("f-appr", "sess-a") == {"running": False, "run_id": None, "approvals": []}


def test_interrupted_runs_are_marked_at_startup(client):
    from kelvo import db
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    with db.conn() as c:
        c.execute("INSERT INTO runs(id,flow_id,session_id,status,started_at) VALUES ('r-old',?, 's', 'running', ?)", (f["id"], db.now()))
    main._mark_interrupted_runs()
    run = [r for r in client.get(f"/api/flows/{f['id']}/runs").json() if r["id"] == "r-old"][0]
    assert run["status"] == "error" and "Interrupted" in run["error"]
