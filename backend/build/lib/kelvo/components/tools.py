from __future__ import annotations

import ast
import html
import ipaddress
import json
import math
import operator
import os
import re
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from .. import db
from .base import DATA, MESSAGE, TEXT, TEXTLIKE, Component, Field, Message, Output

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {k: getattr(math, k) for k in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "floor", "ceil")}
_FUNCS.update(abs=abs, round=round, min=min, max=max)
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expr: str) -> float:
    def ev(n: ast.AST) -> Any:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 1000:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name) and n.id in _CONSTS:
            return _CONSTS[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"unsupported expression: {ast.dump(n)[:60]}")

    return ev(ast.parse(expr.replace("^", "**"), mode="eval"))


class Calculator(Component):
    key = "Calculator"
    display = "Calculator"
    category = "Tools"
    description = "Evaluate an arithmetic expression, e.g. (4 + 4) * 2 or sqrt(16)."
    icon = "calculator"
    tool_default = True
    fields = [Field("expression", "Expression", "str", "2 + 2", tool_param=True, required=True,
                    info="An arithmetic expression such as (3 + 5) * 2")]
    outputs = [Output("result", "Result", DATA)]

    async def out_result(self, ctx) -> dict[str, Any]:
        expr = await ctx.text("expression")
        try:
            v = safe_eval(expr)
        except ZeroDivisionError:
            return {"expression": expr, "error": "division by zero"}
        return {"expression": expr, "result": int(v) if isinstance(v, float) and v.is_integer() else v}


class CurrentDate(Component):
    key = "CurrentDate"
    display = "Current Date"
    category = "Tools"
    description = "Get the current date and time in a time zone."
    icon = "calendar"
    tool_default = True
    fields = [Field("timezone", "Time zone", "str", "UTC", tool_param=True, info="IANA name, e.g. Europe/Lisbon")]
    outputs = [Output("text", "Date", TEXT)]

    async def out_text(self, ctx) -> str:
        tz = await ctx.text("timezone", "UTC") or "UTC"
        try:
            z = ZoneInfo(tz)
        except Exception:
            return f"Unknown time zone '{tz}'."
        return datetime.now(z).strftime(f"%A %Y-%m-%d %H:%M:%S ({tz})")


def _check_public(url: str) -> None:
    if os.environ.get("KELVO_ALLOW_PRIVATE_URLS") == "1":
        return
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Only http(s) URLs are allowed.")
    for info in socket.getaddrinfo(p.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("URLs on private networks are blocked (set KELVO_ALLOW_PRIVATE_URLS=1 to allow).")


def html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|tr)>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


class URLFetch(Component):
    key = "URLFetch"
    display = "URL"
    category = "Tools"
    description = "Fetch a web page and return its readable text."
    icon = "globe"
    tool_default = True
    fields = [
        Field("url", "URL", "str", "https://example.com", tool_param=True, required=True, info="The http(s) URL to fetch"),
        Field("max_chars", "Max characters", "int", 8000, advanced=True),
    ]
    outputs = [Output("text", "Page text", TEXT)]

    async def out_text(self, ctx) -> str:
        url = (await ctx.text("url")).strip()
        _check_public(url)
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "Kelvo/0.1"}) as c:
            r = await c.get(url)
        body = r.text
        if "html" in r.headers.get("content-type", ""):
            body = html_to_text(body)
        return body[: int(await ctx.get("max_chars", 8000))]


class RunFlow(Component):
    key = "RunFlow"
    display = "Run Flow"
    category = "Tools"
    description = "Run another flow as a step or as a tool."
    icon = "workflow"
    tool_output = "message"
    fields = [
        Field("flow", "Flow", "flow", "", required=True),
        Field("input", "Input", "text", "", accepts=TEXTLIKE, tool_param=True, required=True),
    ]
    outputs = [Output("message", "Result", MESSAGE)]

    async def out_message(self, ctx) -> Message:
        from ..engine import Engine  # local import: engine imports components

        flow_id = await ctx.text("flow")
        if flow_id == ctx.engine.flow_id:
            raise ValueError("A flow cannot run itself.")
        with db.conn() as c:
            f = db.row(c.execute("SELECT * FROM flows WHERE id=? OR endpoint_name=?", (flow_id, flow_id)).fetchone(), ("data",))
        if not f:
            raise ValueError("Choose a flow to run.")
        sub = Engine(f, input_value=await ctx.text("input"), session_id=f"{ctx.session_id}:{f['id'][:8]}",
                     depth=ctx.engine.depth + 1, persist=False)
        res = await sub.run()
        texts = [o.get("message", {}).get("text") or o.get("text", "") for o in res["outputs"]]
        return Message(text="\n\n".join(t for t in texts if t), properties={"source": {"display_name": f["name"]}})


__all__ = ["Calculator", "CurrentDate", "URLFetch", "RunFlow", "safe_eval", "json", "TEXTLIKE"]
