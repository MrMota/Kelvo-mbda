import asyncio
import json
import sys

import httpx
import pytest

from kelvo.components import power
from kelvo.components.power import Files, inside, parse_duckduckgo, search

DDG_PAGE = """
<div class="result results_links results_links_deep result--ad"><a class="result__a" href="https://ads.example">Ad</a></div>
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Follama.com%2Fblog&amp;rut=x">Ollama <b>Blog</b></a></h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=x">Run <b>open models</b> &amp; more.</a>
</div>
<div class="result results_links web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="https://example.org/two">Second</a></h2>
  <a class="result__snippet" href="https://example.org/two">Another snippet</a>
</div>
"""


@pytest.fixture()
def mock_net(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        host = request.url.host
        if host == "html.duckduckgo.com":
            return httpx.Response(200, text=DDG_PAGE)
        if host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": [{"title": "B", "url": "https://b.example", "description": "<strong>brave</strong> hit"}]}})
        if host == "api.tavily.com":
            return httpx.Response(200, json={"results": [{"title": "T", "url": "https://t.example", "content": "tavily hit"}]})
        if host == "searx.local":
            return httpx.Response(200, json={"results": [{"title": "S", "url": "https://s.example", "content": "searx hit"}]})
        return httpx.Response(404)

    monkeypatch.setattr(power, "TRANSPORT", httpx.MockTransport(handler))
    return seen


def test_duckduckgo_parsing_skips_ads_and_decodes_links():
    r = parse_duckduckgo(DDG_PAGE)
    assert r == [
        {"title": "Ollama Blog", "url": "https://ollama.com/blog", "snippet": "Run open models & more."},
        {"title": "Second", "url": "https://example.org/two", "snippet": "Another snippet"},
    ]


def test_search_providers(mock_net):
    run = asyncio.run
    assert run(search("duckduckgo", "ollama", 1))[0]["url"] == "https://ollama.com/blog"
    assert run(search("brave", "q", 5, api_key="k"))[0] == {"title": "B", "url": "https://b.example", "snippet": "brave hit"}
    assert mock_net[-1].headers["X-Subscription-Token"] == "k"
    assert run(search("tavily", "q", 5, api_key="t"))[0]["snippet"] == "tavily hit"
    assert mock_net[-1].headers["Authorization"] == "Bearer t"
    assert run(search("searxng", "q", 5, searxng_url="http://searx.local/"))[0]["url"] == "https://s.example"
    with pytest.raises(ValueError, match="API key"):
        run(search("brave", "q", 5))


def test_inside_refuses_escapes(tmp_path):
    root = tmp_path.resolve()
    assert inside(root, "a/b.txt") == root / "a" / "b.txt"
    for bad in ["../x", "/etc/passwd", "a/../../x"]:
        with pytest.raises(PermissionError):
            inside(root, bad)
    (root / "link").symlink_to("/")
    with pytest.raises(PermissionError):
        inside(root, "link/etc")


class _Ctx:
    """Minimal NodeCtx stand-in for toolset tests."""
    def __init__(self, ws, interactive=False, **params):
        class E:
            pass
        self.engine = E()
        self.engine.substitute = lambda v: v
        self.engine.interactive = interactive
        self.answers = []

        async def ask(node_id, tool, what, details):
            self.answers.append(what)
            return interactive
        self.engine.ask_approval = ask
        self.node_id = "files"
        self.params = {"workspace": str(ws), **params}


def tools_of(ctx):
    return {t.name: t for t in Files().toolset(ctx)}


def test_files_tools(tmp_path):
    t = tools_of(_Ctx(tmp_path))
    run = asyncio.run
    assert set(t) == {"list_files", "read_file", "write_file", "edit_file"}
    assert "Created notes/todo.md" in run(t["write_file"].fn({"path": "notes/todo.md", "content": "a\nb\na\n"}))
    assert "notes/todo.md" in run(t["list_files"].fn({}))
    assert run(t["read_file"].fn({"path": "notes/todo.md"})) == "a\nb\na\n"
    assert "appears 2 times" in run(t["edit_file"].fn({"path": "notes/todo.md", "old_text": "a", "new_text": "z"}))
    assert "Edited" in run(t["edit_file"].fn({"path": "notes/todo.md", "old_text": "b\n", "new_text": "B\n"}))
    assert (tmp_path / "notes/todo.md").read_text() == "a\nB\na\n"
    assert "not found" in run(t["edit_file"].fn({"path": "notes/todo.md", "old_text": "nope", "new_text": "x"}))
    with pytest.raises(PermissionError):
        run(t["write_file"].fn({"path": "../escape.txt", "content": "x"}))
    assert not (tmp_path.parent / "escape.txt").exists()


def test_files_read_only_and_write_approval(tmp_path):
    assert set(tools_of(_Ctx(tmp_path, read_only=True))) == {"list_files", "read_file"}
    ctx = _Ctx(tmp_path, interactive=False, approve_writes=True)
    msg = asyncio.run(tools_of(ctx)["write_file"].fn({"path": "x.txt", "content": "hi"}))
    assert "did not approve" in msg and not (tmp_path / "x.txt").exists()
    ctx = _Ctx(tmp_path, interactive=True, approve_writes=True)
    assert "Created" in asyncio.run(tools_of(ctx)["write_file"].fn({"path": "x.txt", "content": "hi"}))
    assert ctx.answers == ["write x.txt"]


def _shell_flow(cmd, approval=True):
    return {"id": "f-shell", "data": {"nodes": [
        {"id": "sh", "type": "component", "position": {"x": 0, "y": 0},
         "data": {"type": "Shell", "params": {"command": cmd, "require_approval": approval}}},
    ], "edges": []}}


def _run_engine(flow, interactive, answer=None):
    from kelvo.engine import Engine, resolve_approval
    events = []

    async def emit(ev, data):
        events.append((ev, data))
        if ev == "approval" and answer is not None:
            asyncio.get_running_loop().call_soon(resolve_approval, data["id"], answer)

    eng = Engine(flow, emit=emit, interactive=interactive, persist=False)
    asyncio.run(eng.run())
    previews = [d["preview"] for e, d in events if e == "node_end"]
    return events, previews


def test_shell_runs_only_when_approved(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    events, out = _run_engine(_shell_flow("echo hello-kelvo"), interactive=True, answer=True)
    assert any(e == "approval" and d["summary"] == "echo hello-kelvo" for e, d in events)
    assert "hello-kelvo" in out[0] and "exit code 0" in out[0]
    _, out = _run_engine(_shell_flow("echo should-not-run"), interactive=True, answer=False)
    assert "did not approve" in out[0] and "should-not-run\n" not in out[0].split("\n", 1)[-1]
    # API / MCP runs have nobody to ask: never executed
    _, out = _run_engine(_shell_flow("echo nope"), interactive=False)
    assert "nobody is watching" in out[0]
    # approval can be switched off; runs in the workspace folder; timeouts stop it
    _, out = _run_engine(_shell_flow("pwd" if sys.platform != "win32" else "cd", approval=False), interactive=False)
    assert str(tmp_path) in out[0]


def test_shell_timeout(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    flow = _shell_flow("sleep 5", approval=False)
    flow["data"]["nodes"][0]["data"]["params"]["timeout"] = 1
    _, out = _run_engine(flow, interactive=False)
    assert "Timed out after 1 s" in out[0]


def test_approval_endpoint(client):
    assert client.post("/api/approvals/nope", json={"approve": True}).status_code == 404


def test_power_agent_template_and_think(client, tmp_path, monkeypatch, mock_net):
    from kelvo.fake_ollama import SEEN_THINK
    from tests.test_app import build, final_messages
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    (tmp_path / "hello.txt").write_text("hi")
    f = client.post("/api/flows", json={"template": "power-agent"}).json()
    evs = build(client, f["id"], "tool:list_files:.")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["name"] == "list_files" and "hello.txt" in steps[0]["output"]
    assert SEEN_THINK[-1] is True  # the template turns thinking on
    evs = build(client, f["id"], "tool:web_search:ollama blog", session="s2")
    steps = [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]
    assert steps[0]["name"] == "web_search" and "https://ollama.com/blog" in steps[0]["output"]
    assert final_messages(evs)[0].startswith("Result:")
