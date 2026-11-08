from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from .. import db, ollama
from .base import (
    DATA,
    EMBEDDINGS,
    MESSAGE,
    STOP,
    TEXT,
    TEXTLIKE,
    Component,
    EmbeddingsConfig,
    Field,
    Message,
    Output,
    to_message,
    to_text,
)


class IfElse(Component):
    key = "IfElse"
    display = "If-Else"
    category = "Logic"
    description = "Route the input to True or False by comparing it with a value."
    icon = "split"
    tool_mode = False
    OPS = ["equals", "not equals", "contains", "starts with", "ends with", "regex", "is empty", "is not empty"]
    fields = [
        Field("input", "Input", "text", "", accepts=TEXTLIKE, required=True),
        Field("operator", "Operator", "select", "contains", options=OPS),
        Field("match", "Match text", "str", ""),
        Field("case_sensitive", "Case sensitive", "bool", False, advanced=True),
        Field("pass_value", "Pass on", "select", "input", options=["input", "match text"], advanced=True),
    ]
    outputs = [Output("true", "True", MESSAGE), Output("false", "False", MESSAGE)]

    async def _decide(self, ctx) -> tuple[bool, Any]:
        raw = await ctx.get("input")
        a, b = to_text(raw), await ctx.text("match")
        if not await ctx.get("case_sensitive", False):
            a, b = a.lower(), b.lower()
        op = await ctx.text("operator", "contains")
        result = {
            "equals": lambda: a.strip() == b.strip(),
            "not equals": lambda: a.strip() != b.strip(),
            "contains": lambda: b in a,
            "starts with": lambda: a.startswith(b),
            "ends with": lambda: a.endswith(b),
            "regex": lambda: re.search(b, a) is not None,
            "is empty": lambda: not a.strip(),
            "is not empty": lambda: bool(a.strip()),
        }.get(op, lambda: False)()
        value = raw if await ctx.text("pass_value", "input") == "input" else await ctx.text("match")
        return result, to_message(value)

    async def out_true(self, ctx) -> Any:
        ok, v = await self._decide(ctx)
        return v if ok else STOP

    async def out_false(self, ctx) -> Any:
        ok, v = await self._decide(ctx)
        return STOP if ok else v


class Parser(Component):
    key = "Parser"
    display = "Parser"
    category = "Processing"
    description = "Format Data or a Message as text with a template like 'Name: {name}'. Use {text} for plain text."
    icon = "scan-text"
    fields = [
        Field("input", "Input", "text", "", accepts=TEXTLIKE, required=True, tool_param=True),
        Field("template", "Template", "text", "{text}", info="Keys of each Data item, or {text}."),
        Field("separator", "Separator", "str", "\n", advanced=True),
    ]
    outputs = [Output("text", "Text", TEXT)]

    async def out_text(self, ctx) -> str:
        v = await ctx.get("input")
        tpl = await ctx.text("template", "{text}") or "{text}"
        sep = (await ctx.get("separator", "\n")).encode().decode("unicode_escape")
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                pass
        items = v if isinstance(v, list) else [v]
        out = []
        for it in items:
            d = it if isinstance(it, dict) else {"text": to_text(it)}
            d = {"text": to_text(it), **d}
            out.append(re.sub(r"\{(\w+)\}", lambda m: to_text(d.get(m.group(1), m.group(0))), tpl))
        return sep.join(out)


class SplitText(Component):
    key = "SplitText"
    display = "Split Text"
    category = "Processing"
    description = "Cut text into overlapping chunks for embedding."
    icon = "scissors"
    tool_mode = False
    fields = [
        Field("input", "Input", "text", "", accepts=TEXTLIKE, required=True, list=True),
        Field("chunk_size", "Chunk size", "int", 1000),
        Field("overlap", "Overlap", "int", 200),
        Field("separator", "Prefer splitting at", "str", "\\n\\n", advanced=True),
    ]
    outputs = [Output("chunks", "Chunks", DATA)]

    async def out_chunks(self, ctx) -> list[dict[str, Any]]:
        items = await ctx.get("input", [])
        text = "\n\n".join(to_text(i) for i in (items if isinstance(items, list) else [items]))
        size = max(50, int(await ctx.get("chunk_size", 1000)))
        overlap = min(max(0, int(await ctx.get("overlap", 200))), size // 2)
        sep = (await ctx.text("separator", "\\n\\n")).encode().decode("unicode_escape") or "\n\n"
        return [{"text": c} for c in split_text(text, size, overlap, sep)]


def split_text(text: str, size: int, overlap: int, sep: str = "\n\n") -> list[str]:
    text = text.strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind(sep, start + size // 2, end)
            if cut == -1:
                cut = text.rfind(" ", start + size // 2, end)
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class MessageHistory(Component):
    key = "MessageHistory"
    display = "Message History"
    category = "Memory"
    description = "Recent chat messages of the current session, as text or Data."
    icon = "history"
    tool_mode = False
    fields = [
        Field("n_messages", "Number of messages", "int", 20),
        Field("session_id", "Session ID", "str", "", advanced=True),
        Field("template", "Line template", "str", "{sender_name}: {text}", advanced=True),
    ]
    outputs = [Output("text", "Text", TEXT), Output("data", "Data", DATA)]

    async def _msgs(self, ctx) -> list[dict[str, Any]]:
        return ctx.engine.history(await ctx.text("session_id") or ctx.session_id, int(await ctx.get("n_messages", 20)))

    async def out_text(self, ctx) -> str:
        tpl = await ctx.text("template") or "{sender_name}: {text}"
        return "\n".join(tpl.format(**{k: m.get(k, "") for k in ("sender_name", "sender", "text")}) for m in await self._msgs(ctx))

    async def out_data(self, ctx) -> list[dict[str, Any]]:
        return [{"sender": m["sender"], "sender_name": m["sender_name"], "text": m["text"], "created_at": m["created_at"]} for m in await self._msgs(ctx)]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class KnowledgeBase(Component):
    key = "KnowledgeBase"
    display = "Knowledge Base"
    category = "Vector Stores"
    description = "A local vector store: ingest chunks, then search them by meaning. Stored in MBDAflow's database."
    icon = "database"
    tool_output = "results"
    fields = [
        Field("collection", "Collection", "str", "default", required=True),
        Field("embedding", "Embeddings", "str", accepts=[EMBEDDINGS], required=True, show_field=False),
        Field("ingest", "Ingest data", "text", "", accepts=TEXTLIKE, list=True, show_field=False,
              info="Connect chunks to add them. Already-stored chunks are skipped."),
        Field("query", "Search query", "text", "", accepts=TEXTLIKE, tool_param=True, info="What to look for"),
        Field("k", "Results", "int", 4),
    ]
    outputs = [Output("results", "Search Results", DATA), Output("context", "Context", TEXT), Output("count", "Ingested", DATA)]

    async def _emb(self, ctx) -> EmbeddingsConfig:
        e = await ctx.get("embedding")
        if not isinstance(e, EmbeddingsConfig):
            raise ValueError("Connect an Ollama Embeddings component.")
        return e

    async def _ingest(self, ctx) -> int:
        if ctx.overrides or not ctx.connected("ingest"):
            return 0
        key = ("ingested", ctx.node_id)
        if key in ctx.engine.memo:
            return ctx.engine.memo[key]
        items = await ctx.get("ingest", [])
        texts = []
        for it in items:
            if isinstance(it, list):
                texts += [to_text(x) for x in it]
            else:
                texts.append(to_text(it))
        texts = [t for t in texts if t.strip()]
        coll = await ctx.text("collection", "default")
        with db.conn() as c:
            have = {r["id"] for r in c.execute("SELECT id FROM vector_chunks WHERE collection=?", (coll,))}
        new = [(hashlib.sha256(f"{coll}\0{t}".encode()).hexdigest()[:32], t) for t in texts]
        new = [(i, t) for i, t in new if i not in have]
        if new:
            emb = await self._emb(ctx)
            vecs: list[list[float]] = []
            for i in range(0, len(new), 32):
                vecs += await ollama.embed(emb.base_url, emb.model, [t for _, t in new[i : i + 32]])
            with db.conn() as c:
                c.executemany(
                    "INSERT OR IGNORE INTO vector_chunks(id,collection,text,metadata,embedding,created_at) VALUES (?,?,?,?,?,?)",
                    [(i, coll, t, json.dumps({"model": emb.model}), json.dumps(v), db.now()) for (i, t), v in zip(new, vecs)],
                )
        ctx.engine.memo[key] = len(new)
        return len(new)

    async def out_count(self, ctx) -> dict[str, Any]:
        n = await self._ingest(ctx)
        return {"ingested": n, "collection": await ctx.text("collection", "default")}

    async def out_results(self, ctx) -> list[dict[str, Any]]:
        await self._ingest(ctx)
        q = await ctx.text("query")
        if not q.strip():
            return []
        emb = await self._emb(ctx)
        [qv] = await ollama.embed(emb.base_url, emb.model, [q])
        coll = await ctx.text("collection", "default")
        with db.conn() as c:
            rs = c.execute("SELECT text, embedding FROM vector_chunks WHERE collection=?", (coll,)).fetchall()
        scored = sorted(((_cos(qv, json.loads(r["embedding"])), r["text"]) for r in rs), reverse=True)
        k = max(1, int(await ctx.get("k", 4)))
        return [{"text": t, "score": round(s, 4)} for s, t in scored[:k]]

    async def out_context(self, ctx) -> str:
        return "\n\n---\n\n".join(r["text"] for r in await self.out_results(ctx))


__all__ = ["IfElse", "Parser", "SplitText", "MessageHistory", "KnowledgeBase", "Message"]
