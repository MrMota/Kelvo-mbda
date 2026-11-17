"""Browser: the agent drives a real browser (Microsoft Edge on Windows) through Playwright.

It opens pages, reads them, and clicks or types using numbered references from the page snapshot,
so small models never have to write CSS selectors. Logins made in this browser are kept in Kelvo's
own browser profile (not your normal Edge profile).
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .. import db
from .base import Component, Field, Output, TEXT, ToolDef

MAX_TEXT = 6000
SNAPSHOT_JS = r"""
() => {
  document.querySelectorAll('[data-kelvo-ref]').forEach(e => e.removeAttribute('data-kelvo-ref'));
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [contenteditable=true], summary';
  const out = []; let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none' || el.disabled) continue;
    n++; el.setAttribute('data-kelvo-ref', String(n));
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    let label = el.getAttribute('aria-label') || el.innerText || (type !== 'password' ? el.value : '') ||
                el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('name') || el.getAttribute('alt') || '';
    label = label.trim().replace(/\s+/g, ' ').slice(0, 80);
    const kind = tag === 'a' ? 'link' : tag === 'input' ? ((type === 'checkbox' || type === 'radio') ? type : (type || 'text') + ' field')
      : tag === 'textarea' ? 'text area' : tag === 'select' ? 'dropdown' : (el.getAttribute('role') || 'button');
    out.push(`[${n}] ${kind} "${label}"` + (tag === 'a' && el.href && !el.href.startsWith('javascript') ? ` -> ${el.href.slice(0, 100)}` : ''));
    if (n >= 150) break;
  }
  return { title: document.title, url: location.href, text: document.body ? document.body.innerText : '', elements: out };
}
"""


_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def _browser_loop() -> asyncio.AbstractEventLoop:
    """Playwright runs on its own event loop thread: on Windows it needs a loop that can start
    subprocesses (Proactor), which the web server's loop may not be."""
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()  # type: ignore[attr-defined]
            threading.Thread(target=loop.run_forever, daemon=True, name="kelvo-browser").start()
            _LOOP = loop
        return _LOOP


async def on_browser(coro):
    return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, _browser_loop()))


def profile_dir() -> Path:
    d = Path(db.db_path()).parent / "browser-profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


class _Session:
    def __init__(self) -> None:
        self.pw = self.context = self.browser = self.page = None

    async def start(self, show: bool, keep_logins: bool) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError("The browser tool needs Playwright. Re-run install.cmd (or: pip install playwright).") from e
        self.pw = await async_playwright().start()
        exe = os.environ.get("KELVO_BROWSER_PATH")
        tries: list[dict[str, Any]] = [{"executable_path": exe}] if exe else []
        tries += [{"channel": "msedge"}, {"channel": "chrome"}, {}] if sys.platform == "win32" else [{"channel": "chrome"}, {"channel": "msedge"}, {}]
        args = ["--no-first-run", "--no-default-browser-check"]
        last: Exception | None = None
        for how in tries:
            try:
                if keep_logins:
                    try:
                        self.context = await self.pw.chromium.launch_persistent_context(
                            str(profile_dir()), headless=not show, args=args, viewport={"width": 1280, "height": 900}, **how)
                    except Exception as e:  # profile in use by another run: fall back to a fresh one
                        if "lock" not in str(e).lower() and "already" not in str(e).lower():
                            raise
                        self.browser = await self.pw.chromium.launch(headless=not show, args=args, **how)
                        self.context = await self.browser.new_context(viewport={"width": 1280, "height": 900})
                else:
                    self.browser = await self.pw.chromium.launch(headless=not show, args=args, **how)
                    self.context = await self.browser.new_context(viewport={"width": 1280, "height": 900})
                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                return
            except Exception as e:
                last = e
        await self.close()
        raise RuntimeError(f"Couldn't start a browser (Edge or Chrome): {last}")

    async def close(self) -> None:
        for obj in (self.context, self.browser):
            try:
                if obj is not None:
                    await obj.close()
            except Exception:
                pass
        if self.pw is not None:
            try:
                await self.pw.stop()
            except Exception:
                pass
        self.pw = self.context = self.browser = self.page = None


async def snapshot(page, max_text: int = MAX_TEXT) -> str:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass
    s = await page.evaluate(SNAPSHOT_JS)
    text = " ".join(s["text"].split()) if s.get("text") else ""
    more = f"\n[… {len(text) - max_text} more characters; call browser_read for the rest with start={max_text}]" if len(text) > max_text else ""
    els = "\n".join(s["elements"]) or "(none)"
    return f"Title: {s['title']}\nURL: {s['url']}\n\nPage text:\n{text[:max_text]}{more}\n\nInteractive elements (use the number as ref):\n{els}"


class Browser(Component):
    key = "Browser"
    display = "Browser"
    category = "Tools"
    description = ("Drive a real browser (Edge on Windows): open pages, read them, click and type. Works on sites that need "
                   "JavaScript or a login. Logins are kept in Kelvo's own browser profile.")
    icon = "app-window"
    tool_default = True
    tool_mode = True
    fields = [
        Field("show_window", "Show the browser window", "bool", False,
              info="Watch the agent work (on the PC running Kelvo). Off = runs invisibly."),
        Field("keep_logins", "Keep logins", "bool", True,
              info="Remember cookies and logins between chats, in Kelvo's own profile (not your normal Edge)."),
        Field("approve_actions", "Ask before clicking or typing", "bool", False,
              info="Each click and each typed text waits for your Approve. Turn on for sites where a click can buy or send something."),
    ]
    outputs = [Output("tools", "Tools", TEXT)]

    async def out_tools(self, ctx) -> str:
        return "Turn on tool mode and connect this to an Agent's Tools."

    def toolset(self, ctx) -> list[ToolDef]:
        eng = ctx.engine
        key = f"browser:{ctx.node_id}"
        show = bool(ctx.params.get("show_window"))
        keep = ctx.params.get("keep_logins", True) is not False
        approve = bool(ctx.params.get("approve_actions"))

        async def page():
            sess: _Session | None = eng.extra.get(key)
            if sess is None or sess.page is None or sess.page.is_closed():
                sess = _Session()
                eng.extra[key] = sess

                async def close(sess=sess):
                    await on_browser(sess.close())
                eng.closers.append(close)
                await on_browser(sess.start(show, keep))
            return sess.page

        async def gate(what: str, details: dict[str, Any]) -> str | None:
            if approve and not await eng.ask_approval(ctx.node_id, "browser", what, details):
                return f"The user did not approve: {what}"
            return None

        def locate(p, ref: Any):
            ref = str(ref or "").strip().strip("[]")
            if not ref.isdigit():
                raise ValueError("ref must be the number of an element from the last snapshot, e.g. 12.")
            return p.locator(f'[data-kelvo-ref="{ref}"]').first

        async def browser_open(a: dict[str, Any]) -> str:
            url = str(a.get("url") or a.get("input") or "").strip()
            if url and "://" not in url:
                url = "https://" + url
            if urlparse(url).scheme not in ("http", "https"):
                return "Only http and https pages can be opened."
            p = await page()

            async def go():
                try:
                    await p.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    return f"Couldn't open {url}: {str(e).splitlines()[0]}"
                return await snapshot(p)
            return await on_browser(go())

        async def browser_read(a: dict[str, Any]) -> str:
            p = await page()
            start = max(0, int(a.get("start") or 0))

            async def read():
                if start:
                    text = " ".join((await p.evaluate("() => document.body ? document.body.innerText : ''")).split())
                    return text[start:start + MAX_TEXT] or "(no more text)"
                return await snapshot(p)
            return await on_browser(read())

        async def browser_click(a: dict[str, Any]) -> str:
            p = await page()
            el = locate(p, a.get("ref") or a.get("input"))

            async def label():
                try:
                    return (await el.inner_text(timeout=3000) if await el.count() else "")[:80]
                except Exception:
                    return ""
            text = await on_browser(label())
            if (msg := await gate(f"click [{a.get('ref')}] {text}".strip(), {"page": p.url, "element": text})):
                return msg

            async def click():
                try:
                    await el.click(timeout=10000)
                except Exception as e:
                    return f"Couldn't click [{a.get('ref')}]: {str(e).splitlines()[0]}. Call browser_read for fresh refs."
                try:
                    await p.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                return await snapshot(p, 3000)
            return await on_browser(click())

        async def browser_type(a: dict[str, Any]) -> str:
            p = await page()
            el = locate(p, a.get("ref"))
            text = str(a.get("text") or "")
            if (msg := await gate(f"type into [{a.get('ref')}]", {"page": p.url, "text": text[:300]})):
                return msg
            async def typ():
                try:
                    tag = await el.evaluate("e => e.tagName.toLowerCase()", timeout=5000)
                    if tag == "select":
                        await el.select_option(label=text, timeout=10000)
                    else:
                        await el.fill(text, timeout=10000)
                    if a.get("submit"):
                        await el.press("Enter", timeout=10000)
                        try:
                            await p.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception:
                            pass
                except Exception as e:
                    return f"Couldn't type into [{a.get('ref')}]: {str(e).splitlines()[0]}. Call browser_read for fresh refs."
                return await snapshot(p, 3000)
            return await on_browser(typ())

        async def browser_back(a: dict[str, Any]) -> str:
            p = await page()

            async def back():
                await p.go_back(wait_until="domcontentloaded", timeout=15000)
                return await snapshot(p, 3000)
            return await on_browser(back())

        obj = lambda **props: {"type": "object", "properties": props, "required": [k for k, v in props.items() if v.pop("_req", False)]}  # noqa: E731
        return [
            ToolDef("browser_open", "Open a web page in the browser; returns its text and numbered interactive elements.",
                    obj(url={"type": "string", "description": "https://… address", "_req": True}), browser_open),
            ToolDef("browser_read", "Read the current page again (fresh element numbers), or more of its text with start.",
                    obj(start={"type": "integer", "description": "Character offset for more text"}), browser_read),
            ToolDef("browser_click", "Click an element by its number from the latest snapshot.",
                    obj(ref={"type": "integer", "description": "Element number, e.g. 12", "_req": True}), browser_click),
            ToolDef("browser_type", "Type into a field (or pick a dropdown option) by element number; submit=true presses Enter.",
                    obj(ref={"type": "integer", "description": "Element number", "_req": True},
                        text={"type": "string", "description": "Text to type, or the option to choose", "_req": True},
                        submit={"type": "boolean", "description": "Press Enter afterwards"}), browser_type),
            ToolDef("browser_back", "Go back to the previous page.", obj(), browser_back),
        ]
