import asyncio
from datetime import datetime

import pytest

from kelvo import memory, schedules
from kelvo.schedules import compute_next


def test_memory_store_and_prompt(client):
    m = memory.add("  Uses   Windows 11 ")
    assert m["text"] == "Uses Windows 11"
    assert memory.add("uses windows 11")["id"] == m["id"]  # no duplicates
    with pytest.raises(ValueError):
        memory.add("   ")
    block = memory.prompt_block()
    assert f"[{m['id'][:8]}] Uses Windows 11" in block and "call `remember`" in block
    assert memory.delete(m["id"][:8]) and memory.all_memories() == []
    assert not memory.delete("zz")  # too short to be safe


def test_memory_api(client):
    a = client.post("/api/memories", json={"text": "Likes short answers"}).json()
    assert client.patch(f"/api/memories/{a['id']}", json={"text": "Likes very short answers"}).json()["text"] == "Likes very short answers"
    assert client.post("/api/memories", json={"text": ""}).status_code == 422
    assert len(client.get("/api/memories").json()) == 1
    client.delete("/api/memories")
    assert client.get("/api/memories").json() == []


def test_agent_remembers_and_forgets(client, tmp_path, monkeypatch):
    from tests.test_app import build
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    f = client.post("/api/flows", json={"template": "power-agent"}).json()
    evs = build(client, f["id"], "tool:remember:Project lives in D:\\code\\kelvo")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["name"] == "remember" and steps[0]["output"].startswith("Remembered [")
    mems = client.get("/api/memories").json()
    assert mems[0]["text"] == "Project lives in D:\\code\\kelvo"
    evs = build(client, f["id"], f"tool:forget:{mems[0]['id'][:8]}", session="s2")
    assert any(e["event"] == "step" and e["data"]["step"].get("output") == "Forgotten." for e in evs)
    assert client.get("/api/memories").json() == []


def test_compute_next():
    wed_10 = datetime(2026, 11, 11, 10, 0)  # a Wednesday
    daily = {"kind": "daily", "time_of_day": "07:30", "days": "0123456"}
    assert compute_next(daily, wed_10) == datetime(2026, 11, 12, 7, 30)  # already passed today → tomorrow
    assert compute_next({**daily, "time_of_day": "18:00"}, wed_10) == datetime(2026, 11, 11, 18, 0)
    assert compute_next({**daily, "days": "0"}, wed_10) == datetime(2026, 11, 16, 7, 30)  # Mondays only
    assert compute_next({**daily, "days": "56"}, wed_10) == datetime(2026, 11, 14, 7, 30)  # weekends
    assert compute_next({"kind": "interval", "every_minutes": 90}, wed_10) == datetime(2026, 11, 11, 11, 30)


def test_schedule_validation(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    url = f"/api/flows/{f['id']}/schedules"
    assert client.post(url, json={"message": "", "kind": "daily", "time_of_day": "07:00"}).status_code == 422
    assert client.post(url, json={"message": "hi", "kind": "daily", "time_of_day": "7am"}).status_code == 422
    assert client.post(url, json={"message": "hi", "kind": "daily"}).status_code == 422
    assert client.post(url, json={"message": "hi", "kind": "interval", "every_minutes": 1}).status_code == 422
    assert client.post(url, json={"message": "hi", "kind": "daily", "time_of_day": "07:00", "days": ""}).status_code == 422
    assert client.post("/api/flows/nope/schedules", json={"message": "hi", "kind": "interval", "every_minutes": 10}).status_code == 404


def test_schedule_runs_into_chat_history(client):
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    s = client.post(f"/api/flows/{f['id']}/schedules", json={"name": "Morning", "message": "Plan my day", "kind": "daily", "time_of_day": "07:00"}).json()
    assert s["next_run"] and s["enabled"] == 1
    r = client.post(f"/api/schedules/{s['id']}/run").json()
    assert r["status"] == "success" and "Question: Plan my day" in r["output"]
    got = client.get("/api/schedules", params={"flow_id": f["id"]}).json()[0]
    assert got["last_status"] == "success" and got["flow_name"] == f["name"] and got["next_run"] > got["last_run"]
    sessions = client.get(f"/api/flows/{f['id']}/sessions").json()
    assert sessions[0]["session_id"] == f"schedule-{s['id']}" and sessions[0]["title"] == "Plan my day"
    # pause: no next run
    assert client.patch(f"/api/schedules/{s['id']}", json={"enabled": False}).json()["next_run"] is None


def test_ticker_runs_due_schedules_once(client):
    from kelvo import db
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    s = client.post(f"/api/flows/{f['id']}/schedules", json={"message": "tick", "kind": "interval", "every_minutes": 30}).json()
    with db.conn() as c:  # pretend the PC was off when it was due
        c.execute("UPDATE schedules SET next_run='2020-01-01T00:00' WHERE id=?", (s["id"],))

    async def go():
        n = await schedules.tick()
        while schedules._running:
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        return n, await schedules.tick()
    first, second = asyncio.run(go())
    assert first == 1 and second == 0  # ran once, then rescheduled into the future
    got = schedules.get(s["id"])
    assert got["last_status"] == "success" and got["next_run"] > datetime.now().isoformat(timespec="minutes")
