"""Single-account login for the editor.

- One account (username + password). No sign-up; a second account is refused.
- First run: set KELVO_USERNAME + KELVO_PASSWORD, or open the app and use the one-time
  setup token printed in the server log, or run `kelvo set-password`.
- Sessions: random token in an HttpOnly, SameSite=Lax cookie; only its sha256 is stored.
- Every /api route needs a session, except auth routes, a minimal health check, and the
  API-key protected /api/v1/run and /mcp.
- Cross-site writes are refused (Origin must match Host) on top of SameSite=Lax.
- Login: 5 failures from one address lock it out for 60 s.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import db

COOKIE = "kelvo_session"
SESSION_DAYS = int(os.environ.get("KELVO_SESSION_DAYS", "30"))
MIN_PASSWORD = 8
PUBLIC_PREFIXES = ("/api/auth/", "/api/v1/")
PUBLIC_EXACT = {"/api/health"}

router = APIRouter()
setup_token: str | None = None
_fails: dict[str, tuple[int, float]] = {}


# ---------------------------------------------------------------- passwords

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    n, r, p = 2**14, 8, 1
    h = hashlib.scrypt(pw.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


def validate_new(username: str, password: str) -> None:
    if not (1 <= len(username) <= 64) or not username.isprintable() or username != username.strip():
        raise HTTPException(422, "Username: 1–64 characters, no leading or trailing spaces.")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"Password: at least {MIN_PASSWORD} characters.")


# ---------------------------------------------------------------- account

def get_user() -> dict | None:
    with db.conn() as c:
        return db.row(c.execute("SELECT * FROM users LIMIT 1").fetchone())


def set_account(username: str, password: str) -> dict:
    """Create the account, or reset it (same or new username). Signs out every session."""
    validate_new(username, password)
    t = db.now()
    with db.conn() as c:
        cur = c.execute("SELECT id FROM users LIMIT 1").fetchone()
        if cur:
            c.execute("UPDATE users SET username=?, password_hash=?, updated_at=? WHERE id=?", (username, hash_password(password), t, cur["id"]))
            c.execute("DELETE FROM sessions WHERE user_id=?", (cur["id"],))
            uid = cur["id"]
        else:
            uid = db.new_id()
            c.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, username, hash_password(password), t, t))
    return {"id": uid, "username": username}


def bootstrap() -> None:
    """Called at startup: env-var account, or a one-time setup token."""
    global setup_token
    if get_user():
        setup_token = None
        return
    u, p = os.environ.get("KELVO_USERNAME"), os.environ.get("KELVO_PASSWORD")
    if u and p:
        set_account(u, p)
        print(f"Kelvo: created the account '{u}' from KELVO_USERNAME / KELVO_PASSWORD.", flush=True)
        setup_token = None
        return
    setup_token = secrets.token_urlsafe(24)
    print(
        "\nKelvo: no account yet. Open the app and enter this one-time setup token:\n"
        f"    {setup_token}\n"
        "(or run `kelvo set-password`, or set KELVO_USERNAME and KELVO_PASSWORD)\n",
        flush=True,
    )


# ---------------------------------------------------------------- sessions

def _hash(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def start_session(response: Response, request: Request, user_id: str) -> None:
    tok = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with db.conn() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(timespec="seconds"),))
        c.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (_hash(tok), user_id, now.isoformat(timespec="seconds"),
                  (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds"), now.isoformat(timespec="seconds")))
    secure = request.url.scheme == "https" or os.environ.get("KELVO_SECURE_COOKIE") == "1"
    response.set_cookie(COOKIE, tok, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/")


def session_user(request: Request) -> dict | None:
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    now = db.now()
    with db.conn() as c:
        r = c.execute(
            "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=? AND s.expires_at > ?",
            (_hash(tok), now),
        ).fetchone()
        if r:
            c.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, _hash(tok)))
    return dict(r) if r else None


# ---------------------------------------------------------------- rate limit

def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


def _check_lock(ip: str) -> None:
    n, until = _fails.get(ip, (0, 0.0))
    if until > time.time():
        raise HTTPException(429, f"Too many attempts. Try again in {int(until - time.time()) + 1} s.")


def _fail(ip: str) -> None:
    n, _ = _fails.get(ip, (0, 0.0))
    n += 1
    _fails[ip] = (0, time.time() + 60) if n >= 5 else (n, 0.0)


# ---------------------------------------------------------------- routes

@router.get("/api/auth/status")
def status(request: Request) -> dict:
    u = session_user(request)
    return {"setup_required": get_user() is None, "authenticated": bool(u), "username": u["username"] if u else None}


@router.post("/api/auth/setup")
def setup(request: Request, response: Response, body: dict = Body(...)) -> dict:
    ip = _client(request)
    _check_lock(ip)
    if get_user():
        raise HTTPException(409, "The account already exists. Sign in instead.")
    if not setup_token or not hmac.compare_digest(str(body.get("token", "")).strip(), setup_token):
        _fail(ip)
        raise HTTPException(403, "That setup token isn't right. Copy it from the server log.")
    user = set_account(str(body.get("username", "")), str(body.get("password", "")))
    _invalidate_setup()
    start_session(response, request, user["id"])
    return {"username": user["username"]}


def _invalidate_setup() -> None:
    global setup_token
    setup_token = None


@router.post("/api/auth/login")
def login(request: Request, response: Response, body: dict = Body(...)) -> dict:
    ip = _client(request)
    _check_lock(ip)
    u = get_user()
    ok = bool(u) and hmac.compare_digest(str(body.get("username", "")), u["username"]) and check_password(str(body.get("password", "")), u["password_hash"])
    if not u:
        check_password("x", hash_password("y"))  # same timing whether or not an account exists
    if not ok:
        _fail(ip)
        raise HTTPException(401, "Wrong username or password.")
    _fails.pop(ip, None)
    start_session(response, request, u["id"])
    return {"username": u["username"]}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    tok = request.cookies.get(COOKIE)
    if tok:
        with db.conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(tok),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/api/account/password")
def change_password(request: Request, response: Response, body: dict = Body(...)) -> dict:
    u = session_user(request)
    full = get_user()
    if not u or not full:
        raise HTTPException(401, "Sign in first.")
    if not check_password(str(body.get("current_password", "")), full["password_hash"]):
        raise HTTPException(403, "Your current password isn't right.")
    username = str(body.get("username") or full["username"])
    set_account(username, str(body.get("new_password", "")))  # signs out every session…
    start_session(response, request, full["id"])  # …then keeps this one signed in
    return {"username": username}


# ---------------------------------------------------------------- middleware

def _same_site(origin: str, request: Request) -> bool:
    """Origin must be this server: its Host, the Host a reverse proxy saw (X-Forwarded-Host),
    or an origin listed in KELVO_ALLOWED_ORIGINS (comma-separated, e.g. https://box.tailnet.ts.net).
    Browsers can't forge Origin, and can't add X-Forwarded-Host cross-site without a CORS
    preflight, which Kelvo refuses for foreign origins."""
    netloc = urlparse(origin).netloc
    hosts = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
    allowed = {o.strip().rstrip("/") for o in os.environ.get("KELVO_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    return netloc in hosts or origin.rstrip("/") in allowed


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)  # SPA, assets, /mcp (API key)
        if path.startswith("/api/v1/"):
            return await call_next(request)  # API key checked by the route
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and not _same_site(origin, request):
                return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
        if path.startswith("/api/auth/") or path in PUBLIC_EXACT:
            return await call_next(request)
        if not session_user(request):
            return JSONResponse({"detail": "Sign in to continue."}, status_code=401)
        return await call_next(request)
