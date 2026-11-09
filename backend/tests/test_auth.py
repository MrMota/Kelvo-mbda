from kelvo import auth


def test_everything_needs_a_session(client):
    client.post("/api/auth/logout")
    for path in ["/api/flows", "/api/skills", "/api/variables", "/api/api-keys", "/api/settings", "/api/components"]:
        assert client.get(path).status_code == 401, path
    assert client.post("/api/flows", json={"name": "x"}).status_code == 401
    assert client.get("/api/health").json() == {"ok": True}  # no Ollama URL leaks while signed out
    assert client.get("/api/auth/status").json() == {"setup_required": False, "authenticated": False, "username": None}


def test_login_logout(client):
    assert client.get("/api/auth/status").json()["username"] == "me"
    client.post("/api/auth/logout")
    assert client.get("/api/flows").status_code == 401
    assert client.post("/api/auth/login", json={"username": "me", "password": "wrong pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "you", "password": "correct horse"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/flows").status_code == 200


def test_lockout_after_five_failures(client):
    client.post("/api/auth/logout")
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "me", "password": "nope nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"})
    assert r.status_code == 429  # even the right password waits out the lock


def test_cross_site_write_refused(client):
    r = client.post("/api/flows", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/flows", json={"name": "x"}, headers={"Origin": "http://testserver"}).status_code == 200


def test_setup_token_flow_and_single_account(fresh):
    assert fresh.get("/api/auth/status").json()["setup_required"] is True
    assert fresh.get("/api/flows").status_code == 401
    bad = fresh.post("/api/auth/setup", json={"token": "guess", "username": "me", "password": "longenough"})
    assert bad.status_code == 403
    assert fresh.post("/api/auth/setup", json={"token": auth.setup_token, "username": "me", "password": "short"}).status_code == 422
    tok = auth.setup_token
    ok = fresh.post("/api/auth/setup", json={"token": tok, "username": "me", "password": "longenough"})
    assert ok.status_code == 200 and fresh.get("/api/flows").status_code == 200
    # the token is single-use and a second account can't be made
    assert fresh.post("/api/auth/setup", json={"token": tok, "username": "two", "password": "longenough"}).status_code == 409
    assert auth.setup_token is None


def test_change_password_signs_out_other_sessions(client, fake_ollama_url):
    from fastapi.testclient import TestClient

    from kelvo.main import app

    other = TestClient(app)
    assert other.post("/api/auth/login", json={"username": "me", "password": "correct horse"}).status_code == 200
    assert client.post("/api/account/password", json={"current_password": "wrong", "new_password": "new password 1"}).status_code == 403
    assert client.post("/api/account/password", json={"current_password": "correct horse", "new_password": "new password 1"}).status_code == 200
    assert client.get("/api/flows").status_code == 200  # this session stays
    assert other.get("/api/flows").status_code == 401  # the other one is gone
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "me", "password": "new password 1"}).status_code == 200


def test_password_hashing():
    h = auth.hash_password("secret pw")
    assert h.startswith("scrypt$") and "secret" not in h
    assert auth.check_password("secret pw", h) and not auth.check_password("secret pX", h)


def test_api_key_routes_unchanged(client):
    key = client.post("/api/api-keys", json={"name": "k"}).json()["key"]
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    client.post("/api/auth/logout")
    assert client.post(f"/api/v1/run/{f['id']}", headers={"x-api-key": key}, json={"input_value": "hi"}).status_code == 200
    assert client.post("/mcp", headers={"x-api-key": key}, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 200


def test_proxy_origins(client, monkeypatch):
    # behind a proxy that rewrites Host, the forwarded host still counts as same-site
    r = client.post("/api/flows", json={"name": "p"}, headers={"Origin": "https://box.tail.ts.net", "X-Forwarded-Host": "box.tail.ts.net"})
    assert r.status_code == 200
    assert client.post("/api/flows", json={"name": "p"}, headers={"Origin": "https://box.tail.ts.net"}).status_code == 403
    monkeypatch.setenv("KELVO_ALLOWED_ORIGINS", "https://box.tail.ts.net")
    assert client.post("/api/flows", json={"name": "p"}, headers={"Origin": "https://box.tail.ts.net/"}).status_code == 200


def test_backup_command(client, tmp_path, monkeypatch, capsys):
    import sqlite3

    from kelvo.cli import backup
    from kelvo import db

    client.post("/api/flows", json={"name": "keep me"})
    backup(None, keep=2)
    backup(None, keep=2)
    import time; time.sleep(1.1)
    backup(None, keep=2)
    folder = tmp_path / "backups"
    files = sorted(folder.glob("kelvo-*.db"))
    assert len(files) == 2  # rotation kept the newest two
    names = [r[0] for r in sqlite3.connect(files[-1]).execute("SELECT name FROM flows")]
    assert "keep me" in names
    out = backup(str(tmp_path / "one.db"), keep=0)
    assert (tmp_path / "one.db").exists() and "integrity ok" in capsys.readouterr().out


def test_secure_cookie_for_https_setups(client, monkeypatch):
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"})
    assert "secure" not in r.headers["set-cookie"].lower()
    monkeypatch.setenv("KELVO_SECURE_COOKIE", "1")
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"})
    assert "secure" in r.headers["set-cookie"].lower()  # testserver: not loopback → Secure
    # the PC itself on http://127.0.0.1 keeps a normal cookie, so local sign-in still works
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"}, headers={"Host": "127.0.0.1:7860"})
    assert "secure" not in r.headers["set-cookie"].lower()
    # behind a proxy that reports HTTPS, always Secure
    monkeypatch.delenv("KELVO_SECURE_COOKIE")
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"}, headers={"X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_tailscale_and_home_wifi_side_by_side(client, monkeypatch):
    """With phone-over-Tailscale enabled (KELVO_SECURE_COOKIE=1), home Wi-Fi (plain http) must still sign in."""
    monkeypatch.setenv("KELVO_SECURE_COOKIE", "1")
    client.post("/api/auth/logout")
    wifi = {"Host": "192.168.1.50:7860", "Origin": "http://192.168.1.50:7860"}
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"}, headers=wifi)
    assert r.status_code == 200 and "secure" not in r.headers["set-cookie"].lower()
    ts = {"Host": "pc.tail1.ts.net", "Origin": "https://pc.tail1.ts.net"}
    r = client.post("/api/auth/login", json={"username": "me", "password": "correct horse"}, headers=ts)
    assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()
