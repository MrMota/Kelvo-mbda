"""Browser tool against a local page, with the sandbox's Chromium."""
import asyncio
import http.server
import os
import shutil
import threading

import pytest

from kelvo.components.browser import Browser
from tests.test_power import _Ctx

CHROMIUM = os.environ.get("KELVO_TEST_CHROMIUM", "/opt/pw-browsers/chromium")
PAGE = b"""<!doctype html><html><head><title>Shop</title></head><body>
<h1>Welcome to the test shop</h1>
<a href="/second">Second page</a>
<form action="/search" method="get"><input name="q" placeholder="Search products"><button>Go</button></form>
<button style="display:none">Hidden</button>
</body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE if self.path == "/" else f"<title>{self.path}</title><p>You are on {self.path}</p>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.mark.skipif(not (shutil.which(CHROMIUM) or os.path.exists(CHROMIUM)), reason="no Chromium here")
def test_browser_tools(tmp_path, monkeypatch, client):
    monkeypatch.setenv("KELVO_BROWSER_PATH", CHROMIUM)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    from kelvo.engine import Engine

    eng = Engine({"id": "f-b", "data": {"nodes": [], "edges": []}}, session_id="b")
    ctx = _Ctx(tmp_path, keep_logins=False)
    ctx.engine = eng
    ctx.node_id = "br"
    tools = {t.name: t for t in Browser().toolset(ctx)}

    async def go():
        try:
            snap = await tools["browser_open"].fn({"url": base + "/"})
            assert "Title: Shop" in snap and "Welcome to the test shop" in snap
            assert '[1] link "Second page"' in snap and "Hidden" not in snap
            ref = next(line for line in snap.splitlines() if "text field" in line).split("]")[0].strip("[")
            out = await tools["browser_type"].fn({"ref": int(ref), "text": "kettle", "submit": True})
            assert "/search?q=kettle" in out
            out = await tools["browser_back"].fn({})
            assert "Title: Shop" in out
            out = await tools["browser_click"].fn({"ref": 1})
            assert "You are on /second" in out
            assert "Only http" in await tools["browser_open"].fn({"url": "file:///etc/passwd"})
        finally:
            for close in eng.closers:
                await close()
    asyncio.run(go())
    srv.shutdown()
