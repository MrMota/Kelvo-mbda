from __future__ import annotations

import json
from typing import Any

from .. import db, ollama
from .base import (
    DATA,
    EMBEDDINGS,
    LLM,
    MESSAGE,
    TEXTLIKE,
    Component,
    EmbeddingsConfig,
    Field,
    LLMConfig,
    Message,
    Output,
)

MODEL_FIELDS = [
    Field("model", "Model", "model", "", required=True, info="Any model pulled into your Ollama server."),
    Field("base_url", "Ollama URL", "str", "", advanced=True, placeholder="from Settings", info="Blank = Settings → Models."),
    Field("temperature", "Temperature", "float", 0.2, min=0, max=2, step=0.05),
    Field("num_ctx", "Context window", "int", 0, advanced=True, info="0 = model default."),
    Field("num_predict", "Max tokens", "int", 0, advanced=True, info="0 = no limit."),
    Field("keep_alive", "Keep alive", "str", "", advanced=True, placeholder="5m"),
]


async def llm_from_ctx(ctx, connected_field: str | None = "llm") -> LLMConfig:
    if connected_field and ctx.connected(connected_field):
        cfg = await ctx.get(connected_field)
        if isinstance(cfg, LLMConfig):
            return cfg
    model = await ctx.text("model")
    if not model:
        model = db.get_setting("default_model") or ""
    if not model:
        raise ValueError("Choose a model (or set a default model in Settings → Models).")
    options: dict[str, Any] = {}
    t = await ctx.get("temperature")
    if t is not None and t != "":
        options["temperature"] = float(t)
    for k in ("num_ctx", "num_predict"):
        v = await ctx.get(k)
        if v not in (None, "", 0, "0"):
            options[k] = int(v)
    return LLMConfig(
        base_url=(await ctx.text("base_url") or db.ollama_base_url()).rstrip("/"),
        model=model,
        options=options,
        keep_alive=await ctx.text("keep_alive") or None,
    )


class OllamaModel(Component):
    key = "OllamaModel"
    display = "Ollama"
    category = "Models"
    description = "Generate text with an open model served by Ollama."
    icon = "cpu"
    tool_output = "response"
    fields = [
        Field("input", "Input", "text", "", accepts=TEXTLIKE, tool_param=True, required=True),
        Field("system_message", "System message", "text", "", accepts=TEXTLIKE),
        *MODEL_FIELDS,
        Field("json_mode", "JSON mode", "bool", False, advanced=True),
    ]
    outputs = [Output("response", "Model Response", MESSAGE), Output("model", "Language Model", LLM)]

    async def out_model(self, ctx) -> LLMConfig:
        return await llm_from_ctx(ctx, None)

    async def out_response(self, ctx) -> Message:
        cfg = await llm_from_ctx(ctx, None)
        prompt = await ctx.text("input")
        system = await ctx.text("system_message")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        text = ""
        async for ch in ollama.chat_stream(
            cfg.base_url, cfg.model, messages, options=cfg.options, keep_alive=cfg.keep_alive,
            fmt="json" if await ctx.get("json_mode") else None,
        ):
            tok = (ch.get("message") or {}).get("content") or ""
            if tok:
                text += tok
                if ctx.streaming:
                    await ctx.emit("token", {"chunk": tok})
        return Message(text=text, properties={"source": {"id": ctx.node_id, "display_name": "Ollama", "source": cfg.model}})


class OllamaEmbeddings(Component):
    key = "OllamaEmbeddings"
    display = "Ollama Embeddings"
    category = "Models"
    description = "Turn text into vectors with an Ollama embedding model (e.g. nomic-embed-text)."
    icon = "binary"
    tool_mode = False
    fields = [
        Field("model", "Model", "embed_model", "nomic-embed-text", required=True),
        Field("base_url", "Ollama URL", "str", "", advanced=True, placeholder="from Settings"),
    ]
    outputs = [Output("embeddings", "Embeddings", EMBEDDINGS)]

    async def out_embeddings(self, ctx) -> EmbeddingsConfig:
        return EmbeddingsConfig(
            base_url=(await ctx.text("base_url") or db.ollama_base_url()).rstrip("/"),
            model=await ctx.text("model") or "nomic-embed-text",
        )


SCHEMA_EXAMPLE = json.dumps(
    {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}, "required": ["name"]},
    indent=2,
)


class StructuredOutput(Component):
    key = "StructuredOutput"
    display = "Structured Output"
    category = "Models"
    description = "Extract JSON that matches a schema, using Ollama's structured outputs."
    icon = "table"
    tool_output = "data"
    fields = [
        Field("llm", "Language Model", "str", accepts=[LLM], show_field=False, info="Or set the model below."),
        Field("input", "Input", "text", "", accepts=TEXTLIKE, required=True, tool_param=True),
        Field("instructions", "Instructions", "text", "Extract the requested fields from the input."),
        Field("schema", "JSON Schema", "json", SCHEMA_EXAMPLE),
        Field("model", "Model", "model", "", info="Used when no Language Model is connected."),
        Field("base_url", "Ollama URL", "str", "", advanced=True, placeholder="from Settings"),
        Field("temperature", "Temperature", "float", 0.0, min=0, max=2, step=0.05, advanced=True),
    ]
    outputs = [Output("data", "Data", DATA)]

    async def out_data(self, ctx) -> Any:
        cfg = await llm_from_ctx(ctx, "llm")
        raw = await ctx.get("schema")
        schema = json.loads(raw) if isinstance(raw, str) else raw
        messages = [
            {"role": "system", "content": (await ctx.text("instructions")) + "\nReply with JSON only."},
            {"role": "user", "content": await ctx.text("input")},
        ]
        res = await ollama.chat(cfg.base_url, cfg.model, messages, options=cfg.options, fmt=schema)
        try:
            return json.loads(res["content"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Model did not return valid JSON: {res['content'][:200]}") from e
