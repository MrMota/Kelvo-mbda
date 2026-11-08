import os
import socket
import threading
import time

import pytest


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="session")
def fake_ollama_url():
    import uvicorn

    from kelvo.fake_ollama import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture()
def client(tmp_path, fake_ollama_url, monkeypatch):
    monkeypatch.setenv("KELVO_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("KELVO_REQUIRE_API_KEY", "1")
    from fastapi.testclient import TestClient

    from kelvo import db
    from kelvo.main import app

    with TestClient(app) as c:
        db.set_setting("ollama_base_url", fake_ollama_url)
        db.set_setting("default_model", "llama3.1:8b")
        yield c
