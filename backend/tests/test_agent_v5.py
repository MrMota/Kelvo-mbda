"""0.5.0 agent features: plan checklist, helpers, compaction, speed/memory meter, images, learning skills."""
import base64
import json

from kelvo import db
from tests.test_app import build, final_messages


def done_steps(evs):
    return [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]


def power(client, **agent_params):
    f = client.post("/api/flows", json={"template": "power-agent"}).json()
    data = f["data"]
    for n in data["nodes"]:
        if n["data"].get("type") == "Agent":
            n["data"]["params"].update({"model": "llama3.1:8b", **agent_params})
    return f, data


def test_plan_checklist(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    f, data = power(client)
    steps = json.dumps([{"text": "Look around", "status": "done"}, {"text": "Answer", "status": "in_progress"}])
    evs = build(client, f["id"], f"tool:update_plan:{steps}", data=data)
    plans = [e["data"]["steps"] for e in evs if e["event"] == "plan"]
    assert plans and plans[-1][0] == {"text": "Look around", "status": "done"}
    assert "Plan saved (1/2 done)" in done_steps(evs)[0]["output"]
    msg = [e["data"]["message"] for e in evs if e["event"] == "message"][0]
    assert msg["properties"]["plan"][1]["status"] == "in_progress"


def test_normalize_plan():
    from kelvo.components.agent import normalize_plan

    assert normalize_plan("- [x] one\n- [ ] two\n- [~] three") == [
        {"text": "one", "status": "done"}, {"text": "two", "status": "pending"}, {"text": "three", "status": "in_progress"}]
    assert normalize_plan(["a", "b"])[1] == {"text": "b", "status": "pending"}
    assert normalize_plan([{"step": "x", "status": "completed"}]) == [{"text": "x", "status": "done"}]


def test_helper_sub_agent(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    (tmp_path / "notes.txt").write_text("hello")
    f, data = power(client)
    evs = build(client, f["id"], "tool:delegate:tool:list_files:.", data=data)
    names = [s["name"] for s in done_steps(evs)]
    assert "helper › list_files" in names and "delegate" in names
    report = next(s for s in done_steps(evs) if s["name"] == "delegate")["output"]
    assert report.startswith("Helper report") and "notes.txt" in report
    assert any(e["event"] == "status" and "helper" in e["data"]["text"].lower() for e in evs)


def test_usage_meter(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    evs = build(client, f["id"], "hello there")
    usage = [e["data"] for e in evs if e["event"] == "usage"]
    assert usage and usage[-1]["tokens_per_sec"] == 40.0 and usage[-1]["limit"] == 4096 and usage[-1]["used"] > 20
    msg = [e["data"]["message"] for e in evs if e["event"] == "message"][0]
    assert msg["properties"]["usage"]["tokens_per_sec"] == 40.0


def test_auto_compaction_summarizes_history(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    statuses = []
    for i in range(4):
        evs = build(client, f["id"], f"message {i} " + "words " * 700, session="long")
        statuses.append(any(e["event"] == "status" and "Summarizing" in e["data"]["text"] for e in evs))
    assert statuses[0] is False and any(statuses)  # the first turn fits; later ones summarize
    with db.conn() as c:
        rs = c.execute("SELECT * FROM messages WHERE session_id='long' AND sender_name='Summary'").fetchall()
    assert rs and rs[0]["text"].startswith("Summary:")
    # the next run starts from the summary instead of all the old messages
    evs = build(client, f["id"], "again", session="long")
    assert "[history=3]" in final_messages(evs)[0] and not any(e["event"] == "status" and "Summarizing" in e["data"]["text"] for e in evs)


def test_compact_button(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    assert client.post(f"/api/flows/{f['id']}/compact", json={"session_id": "c"}).status_code == 400
    for i in range(3):
        build(client, f["id"], f"turn {i}", session="c")
    r = client.post(f"/api/flows/{f['id']}/compact", json={"session_id": "c"})
    assert r.status_code == 200 and r.json()["properties"]["summary"] is True
    msgs = client.get(f"/api/flows/{f['id']}/messages?session_id=c").json()
    assert msgs[-3]["sender_name"] == "Summary"  # placed before the two newest messages
    evs = build(client, f["id"], "next", session="c")
    assert "[history=3]" in final_messages(evs)[0]  # summary + last two, not all six


PNG = base64.b64encode(bytes.fromhex("89504e470d0a1a0a0000000d4948445200000008000000080806000000c40fbe8b0000001249444154789c63d0cf7ff21f1f6618190a004a36a041196caea90000000049454e44ae426082")).decode()


def test_images_go_to_vision_models(client):
    from kelvo.fake_ollama import SEEN_IMAGES

    up = client.post("/api/uploads", json={"name": "shot.png", "data": PNG}).json()
    assert up["kind"] == "image" and not up.get("warning")
    raw = client.get(f"/api/uploads/{up['id']}/file")
    assert raw.status_code == 200 and raw.headers["content-type"] == "image/png"
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    data = f["data"]
    for n in data["nodes"]:
        if n["data"].get("type") == "Agent":
            n["data"]["params"]["model"] = "qwen2.5:7b"  # has vision
    r = client.post(f"/api/flows/{f['id']}/build", json={"input_value": "what is this?", "session_id": "img", "data": data, "files": [up["id"]]})
    assert r.status_code == 200 and SEEN_IMAGES[-1] == 1
    data["nodes"] = [n if n["data"].get("type") != "Agent" else {**n, "data": {**n["data"], "params": {**n["data"]["params"], "model": "llama3.1:8b"}}}
                     for n in data["nodes"]]
    r = client.post(f"/api/flows/{f['id']}/build", json={"input_value": "and this?", "session_id": "img2", "data": data, "files": [up["id"]]})
    assert SEEN_IMAGES[-1] == 0 and "can't see images" in r.text


def test_upload_file_route_serves_images_only(client):
    up = client.post("/api/uploads", json={"name": "page.html", "data": base64.b64encode(b"<script>x</script>").decode()}).json()
    assert client.get(f"/api/uploads/{up['id']}/file").status_code == 404
    assert client.get("/api/uploads/not-an-id/file").status_code == 404


def test_learn_skill_needs_approval(client, tmp_path, monkeypatch):
    import asyncio

    from kelvo.components.agent import save_skill_tool

    class E:
        interactive = False
    class C:
        engine = E()
        node_id = "agent"
    tool = save_skill_tool(C())
    args = {"name": "Weekly Report", "description": "Use when asked for the weekly report", "instructions": "1. Do it"}
    assert "nobody is watching" in asyncio.run(tool.fn(args))
    asked = []

    async def ask(node_id, kind, what, details):
        asked.append((kind, details["name"]))
        return True
    C.engine.interactive = True
    C.engine.ask_approval = ask
    assert "saved" in asyncio.run(tool.fn(args))
    assert asked == [("skill", "weekly-report")]
    assert any(s["name"] == "weekly-report" for s in client.get("/api/skills").json())
    assert "updated" in asyncio.run(tool.fn({**args, "instructions": "2. Better"}))
