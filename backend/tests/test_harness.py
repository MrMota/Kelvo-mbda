"""0.5.0: checkpoints/undo, approval rules, search tools, AGENTS.md, diffs."""
import asyncio

from kelvo import checkpoints, db, rules
from kelvo.components.power import Files
from tests.test_power import _Ctx, _run_engine, _shell_flow, tools_of


class _E:
    pass


def _ctx_with_engine(ws, **params):
    """A Files ctx whose engine keeps checkpoints like the real one."""
    from kelvo.engine import Engine

    ctx = _Ctx(ws, interactive=True, **params)
    eng = Engine({"id": "f-cp", "data": {"nodes": [], "edges": []}}, session_id="s-cp", interactive=True)
    eng.ask_approval = ctx.engine.ask_approval
    ctx.engine = eng
    return ctx, eng


def test_search_and_find(client, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return compute_total(3)\n")
    (tmp_path / "src" / "util.py").write_text("def compute_total(n):\n    return n * 2\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("compute_total")
    t = tools_of(_Ctx(tmp_path))
    out = asyncio.run(t["search_files"].fn({"query": "compute_total"}))
    assert "src/app.py:2:" in out and "src/util.py:1:" in out and "node_modules" not in out
    out = asyncio.run(t["search_files"].fn({"query": r"def \w+\(n\)", "regex": True, "file_pattern": "*.py"}))
    assert "src/util.py:1:" in out and "app.py" not in out
    assert asyncio.run(t["find_files"].fn({"pattern": "util*"})).strip() == "src/util.py"
    assert "src/app.py" in asyncio.run(t["find_files"].fn({"pattern": "*.py"}))


def test_checkpoints_and_undo(client, tmp_path):
    (tmp_path / "keep.txt").write_text("original")
    ctx, eng = _ctx_with_engine(tmp_path)
    eng.run_id = "run-1"
    t = {x.name: x for x in Files().toolset(ctx)}
    run = asyncio.run
    run(t["edit_file"].fn({"path": "keep.txt", "old_text": "original", "new_text": "changed"}))
    run(t["write_file"].fn({"path": "keep.txt", "content": "changed twice"}))
    run(t["write_file"].fn({"path": "new/made.txt", "content": "fresh"}))
    assert (tmp_path / "keep.txt").read_text() == "changed twice"
    ch = checkpoints.changes("run-1")
    assert [c["created"] for c in ch] == [False, True] and len(eng.changed_files) == 2
    res = client.post("/api/runs/run-1/undo").json()
    assert len(res["restored"]) == 2 and not res["skipped"]
    assert (tmp_path / "keep.txt").read_text() == "original" and not (tmp_path / "new" / "made.txt").exists()
    assert all(c["restored"] for c in client.get("/api/runs/run-1/changes").json())
    assert client.post("/api/runs/nope/undo").status_code == 404


def test_diff_in_approval(tmp_path):
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n")
    seen = []
    ctx = _Ctx(tmp_path, interactive=True, approve_writes=True)

    async def ask(node_id, tool, what, details):
        seen.append(details)
        return True
    ctx.engine.ask_approval = ask
    t = tools_of(ctx)
    asyncio.run(t["edit_file"].fn({"path": "a.txt", "old_text": "two", "new_text": "TWO"}))
    assert "-two" in seen[0]["diff"] and "+TWO" in seen[0]["diff"]


def test_rules_matching(client):
    assert rules.matches("npm test", "npm test*") and rules.matches("npm test -- -k x", "npm test*")
    assert not rules.matches("npm test && del /q *", "npm test*")  # chaining never rides on a wildcard
    assert not rules.matches("npm testx", "npm test")
    assert rules.blocked("diskpart") and rules.blocked("cmd /c format C: /q")
    assert rules.suggest("npm run build --prod") == "npm run*" and rules.suggest("python build.py") == "python build.py"
    assert rules.allowed("git status") and not rules.allowed("git push")
    r = client.put("/api/approval-rules", json={"allow": ["pytest*", "pytest*", ""], "block": ["*shutdown*"]}).json()
    assert r["allow"] == ["pytest*"] and r["block"] == ["*shutdown*"]
    assert rules.allowed("pytest -q tests") and not rules.allowed("git status")


def test_shell_allow_and_block(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    rules.save(allow=["echo allowed*"], block=["*forbidden*"])
    _, out = _run_engine(_shell_flow("echo allowed-run"), interactive=False)  # nobody watching, but allowed
    assert "allowed-run" in out[0] and "exit code 0" in out[0]
    _, out = _run_engine(_shell_flow("echo forbidden", approval=False), interactive=False)
    assert "Blocked by your rules" in out[0]


def test_allow_in_this_chat(client, tmp_path, monkeypatch):
    """Answering 'allow in this chat' stops further questions for matching commands in that chat."""
    from kelvo.engine import CHAT_GRANTS, Engine, resolve_approval

    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    rules.save(allow=[], block=[])
    CHAT_GRANTS.clear()
    asked = []

    async def go(cmd):
        async def emit(ev, data):
            if ev == "approval":
                asked.append(data["details"]["suggest"])
                asyncio.get_running_loop().call_soon(resolve_approval, data["id"], True, "chat", "echo hi*")
        eng = Engine(_shell_flow(cmd), session_id="chat-1", emit=emit, interactive=True, persist=False)
        await eng.run()
        return eng
    asyncio.run(go("echo hi one"))
    asyncio.run(go("echo hi two"))
    assert len(asked) == 1 and CHAT_GRANTS


def test_project_instructions(tmp_path):
    from kelvo.components.power import project_instructions

    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "AGENTS.md").write_text("Run tests with: pytest -q")
    (proj / "src" / "a.py").write_text("x = 1")
    e = _E()
    e.loaded_instructions = set()
    assert "pytest -q" in project_instructions(e, proj / "src" / "a.py")
    assert project_instructions(e, proj / "src") == ""  # only once
    ctx = _Ctx(tmp_path, access="whole computer")
    ctx.engine.loaded_instructions = set()
    out = asyncio.run(tools_of(ctx)["read_file"].fn({"path": str(proj / "src" / "a.py")}))
    assert out.startswith("x = 1") and "Project instructions from" in out
