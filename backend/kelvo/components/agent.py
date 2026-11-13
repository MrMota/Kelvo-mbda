"""Agent with tool calling on Ollama, plus Skills: instruction packs loaded on demand."""
from __future__ import annotations

import json
import re
from typing import Any

from .. import db, ollama
from .base import (
    LLM,
    MESSAGE,
    SKILL,
    TEXTLIKE,
    TOOL,
    Component,
    Field,
    Message,
    Output,
    SkillDef,
    ToolDef,
)
from .models import MODEL_FIELDS, llm_from_ctx

DEFAULT_INSTRUCTIONS = "You are a helpful assistant. Use your tools when they help, and answer clearly."


def load_library_skills(names: list[str] | str | None) -> list[SkillDef]:
    if not names:
        return []
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    with db.conn() as c:
        if "*" in names:
            rs = c.execute("SELECT name, description, body FROM skills ORDER BY name").fetchall()
        else:
            q = ",".join("?" * len(names))
            rs = c.execute(f"SELECT name, description, body FROM skills WHERE name IN ({q}) ORDER BY name", names).fetchall()
    return [SkillDef(r["name"], r["description"], r["body"]) for r in rs]


def skills_prompt(skills: list[SkillDef]) -> str:
    lines = [
        "",
        "## Skills",
        "You have skills: packs of expert instructions. Only their names and descriptions are listed here.",
        "When a request matches a skill, call the `load_skill` tool with its name FIRST, then follow the instructions it returns.",
        "",
    ]
    lines += [f"- {s.name}: {s.description}" for s in skills]
    return "\n".join(lines)


def skill_tool(skills: list[SkillDef]) -> ToolDef:
    by_name = {s.name: s for s in skills}

    async def load(args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        s = by_name.get(name)
        if s is None:
            return f"No skill named '{name}'. Available: {', '.join(by_name)}"
        return f"# Skill: {s.name}\n\n{s.body}"

    return ToolDef(
        name="load_skill",
        description="Load the full instructions of one of your skills by name.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "enum": list(by_name), "description": "Skill name"}},
            "required": ["name"],
        },
        fn=load,
    )


# ---------------------------------------------------------------- keeping the agent loop on track

MAX_NUDGES = 2
OLLAMA_DEFAULT_CTX = 4096  # Ollama's usual context when none is set; set Context window on the Agent for more
NUDGE = ("You described what you would do, but you did not call a tool, so nothing happened. "
         "If a tool is needed, call it now. If the task is complete, reply with your final answer.")
_ANNOUNCE = re.compile(
    r"\b(i'?ll|i will|i'?m going to|i am going to|let me|let'?s|i'?m about to|i'?m now|now i'?ll|next,? i|first,? i|"
    r"i need to|i should|i can now|going to)\b", re.I)
_CLOSING = re.compile(r"\b(let me know|feel free|hope (this|that) helps|anything else)\b", re.I)


def looks_unfinished(text: str) -> bool:
    """A reply that announces an action instead of giving an answer (or is empty)."""
    t = text.strip()
    if not t:
        return True
    tail = t[-400:]
    if t.endswith("?") or _CLOSING.search(tail):
        return False
    return bool(_ANNOUNCE.search(tail)) or t.endswith((":", "...", "…"))


_TAGGED = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def parse_text_tool_calls(content: str, tools: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Some local models print the tool call instead of making it. Recover those for tools that exist."""
    calls, spans = [], []
    candidates = [(m.group(1), m.span()) for m in _TAGGED.finditer(content)] or \
                 [(m.group(1), m.span()) for m in _FENCED.finditer(content)]
    if not candidates and content.strip().startswith("{"):
        candidates = [(content.strip(), (0, len(content)))]
    for raw, span in candidates:
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("name") not in tools:
            continue
        args = obj.get("arguments", obj.get("parameters", {}))
        calls.append({"function": {"name": obj["name"], "arguments": args if isinstance(args, dict) else _args(args)}})
        spans.append(span)
    if not calls:
        return [], content
    for a, b in reversed(spans):
        content = content[:a] + content[b:]
    return calls, content.strip()


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    chars = sum(len(str(m.get("content") or "")) + 12 for m in messages)
    chars += sum(len(json.dumps(m.get("tool_calls"))) for m in messages if m.get("tool_calls"))
    return int(chars / 3.5)


def fit_context(messages: list[dict[str, Any]], limit: int) -> tuple[int, int]:
    """Keep the conversation inside the context window by shortening the OLDEST tool outputs first
    (the last two stay whole). Otherwise Ollama silently drops the start, often the instructions."""
    budget = int(limit * 0.8)
    used = estimate_tokens(messages)
    trimmed = 0
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"][:-2]
    for i in tool_idx:
        if used <= budget:
            break
        text = str(messages[i].get("content") or "")
        if len(text) <= 300:
            continue
        messages[i]["content"] = text[:200] + f"\n[… {len(text) - 200} characters of this earlier tool output were removed to fit the context window]"
        trimmed += 1
        used = estimate_tokens(messages)
    return used, trimmed


def memory_tools() -> list[ToolDef]:
    from .. import memory as ltm

    async def remember(a: dict[str, Any]) -> str:
        try:
            m = ltm.add(str(a.get("fact") or a.get("input") or ""))
        except ValueError as e:
            return str(e)
        return f"Remembered [{m['id'][:8]}]: {m['text']}"

    async def forget(a: dict[str, Any]) -> str:
        mid = str(a.get("memory_id") or a.get("input") or "")
        return "Forgotten." if ltm.delete(mid) else f"No single memory matches '{mid}'. Use an id from the memory list."

    return [
        ToolDef("remember", "Save a lasting fact or preference about the user for future chats.",
                {"type": "object", "properties": {"fact": {"type": "string", "description": "One short fact, e.g. 'Uses Windows 11 with an RTX 5090'"}}, "required": ["fact"]}, remember),
        ToolDef("forget", "Delete a memory that is wrong or outdated.",
                {"type": "object", "properties": {"memory_id": {"type": "string", "description": "The id shown in brackets, e.g. 3f9a1c2b"}}, "required": ["memory_id"]}, forget),
    ]


def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {"input": v}
        except json.JSONDecodeError:
            return {"input": raw}
    return {}


def _dedupe(tools: list[ToolDef]) -> list[ToolDef]:
    seen: dict[str, int] = {}
    out = []
    for t in tools:
        n = seen.get(t.name, 0)
        seen[t.name] = n + 1
        if n:
            t = ToolDef(f"{t.name}_{n + 1}", t.description, t.parameters, t.fn)
        out.append(t)
    return out


class Agent(Component):
    key = "Agent"
    display = "Agent"
    category = "Agents"
    description = "An agent that reasons with an Ollama model, calls tools and loads skills."
    icon = "bot"
    tool_output = "response"
    fields = [
        Field("input", "Input", "text", "", accepts=TEXTLIKE, tool_param=True, required=True,
              info="The task or question for the agent."),
        Field("system_prompt", "Agent instructions", "text", DEFAULT_INSTRUCTIONS, accepts=TEXTLIKE),
        Field("tools", "Tools", "str", accepts=[TOOL], list=True, show_field=False),
        Field("skills", "Skills", "str", accepts=[SKILL], list=True, show_field=False),
        Field("library_skills", "Library skills", "skills", [], info="Skills from your library this agent can load."),
        Field("llm", "Language Model", "str", accepts=[LLM], show_field=False, info="Optional: overrides the model below."),
        *MODEL_FIELDS,
        Field("think", "Think before answering", "bool", False,
              info="Reasoning models (qwen3, deepseek-r1…) work the problem through first: slower, smarter."),
        Field("long_term_memory", "Long-term memory", "bool", False,
              info="Remember facts about you across chats (Settings → Memory)."),
        Field("memory", "Chat memory", "bool", True, advanced=True, info="Include this session's earlier messages."),
        Field("n_messages", "Messages to remember", "int", 20, advanced=True),
        Field("max_iterations", "Max tool rounds", "int", 20, advanced=True,
              info="How many rounds of tool calls before the agent must answer. Each round can call several tools."),
    ]
    outputs = [Output("response", "Response", MESSAGE)]

    async def out_response(self, ctx) -> Message:
        cfg = await llm_from_ctx(ctx, "llm")
        task = await ctx.text("input")
        system = await ctx.text("system_prompt") or DEFAULT_INSTRUCTIONS

        skills: list[SkillDef] = [s for s in await ctx.get("skills", []) if isinstance(s, SkillDef)]
        skills += [s for s in load_library_skills(await ctx.get("library_skills")) if s.name not in {x.name for x in skills}]
        tools: list[ToolDef] = [t for t in await ctx.get("tools", []) if isinstance(t, ToolDef)]
        if skills:
            system += "\n" + skills_prompt(skills)
            tools.append(skill_tool(skills))
        if await ctx.get("long_term_memory", False) and not ctx.overrides:
            from .. import memory as ltm

            system += "\n" + ltm.prompt_block()
            tools += memory_tools()
        tools = _dedupe(tools)
        by_name = {t.name: t for t in tools}

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        is_top_level = not ctx.overrides  # a tool-call run of a sub-agent gets no chat memory
        if is_top_level and await ctx.get("memory", True):
            for m in ctx.engine.history(ctx.session_id, int(await ctx.get("n_messages", 20))):
                messages.append({"role": "user" if m["sender"] == "user" else "assistant", "content": m["text"]})
        messages.append({"role": "user", "content": task})

        steps: list[dict[str, Any]] = []
        max_rounds = max(1, int(await ctx.get("max_iterations", 20)))
        ctx_limit = int(cfg.options.get("num_ctx") or OLLAMA_DEFAULT_CTX)
        final = ""
        think = True if await ctx.get("think", False) else None
        rounds = nudges = 0
        warned = False
        all_thinking = ""
        while True:
            offer = bool(tools) and rounds < max_rounds
            used, trimmed = fit_context(messages, ctx_limit)
            if (trimmed or used > 0.85 * ctx_limit) and not warned and is_top_level:
                warned = True
                await ctx.emit("context_warning", {"used": used, "limit": ctx_limit, "trimmed": trimmed})
            content, thinking, calls = "", "", []
            async for ch in ollama.chat_stream(cfg.base_url, cfg.model, messages, tools=[t.schema() for t in tools] if offer else None,
                                               options=cfg.options, keep_alive=cfg.keep_alive, think=think):
                m = ch.get("message") or {}
                th = m.get("thinking") or ""
                if th:
                    thinking += th
                    all_thinking += th
                    if ctx.streaming:
                        await ctx.emit("thinking", {"chunk": th})
                tok = m.get("content") or ""
                if tok:
                    content += tok
                    if ctx.streaming:
                        await ctx.emit("token", {"chunk": tok})
                calls += m.get("tool_calls") or []
            if not calls and offer:
                calls, content = parse_text_tool_calls(content, by_name)  # tool calls the model wrote out as text
            if not calls:
                if offer and nudges < MAX_NUDGES and looks_unfinished(content):
                    # It said what it would do (or said nothing) but called no tool: remind it, don't stop.
                    nudges += 1
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": NUDGE})
                    await ctx.emit("status", {"text": "Reminding the model to actually use its tools…"})
                    if ctx.streaming:
                        await ctx.emit("token_reset", {})
                    continue
                final = content
                break
            rounds += 1
            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            for call in calls:
                fn = call.get("function") or {}
                name, args = fn.get("name", ""), _args(fn.get("arguments"))
                step: dict[str, Any] = {"type": "tool", "name": name, "input": args}
                await ctx.emit("step", {"step": {**step, "status": "running"}})
                tool = by_name.get(name)
                if tool is None:
                    result, step["error"] = f"Unknown tool '{name}'. Available: {', '.join(by_name)}", True
                else:
                    try:
                        result = await tool.fn(args)
                    except Exception as e:  # tool errors go back to the model, not up the stack
                        result, step["error"] = f"Tool error: {e}", True
                step["output"] = result[:4000]
                steps.append(step)
                await ctx.emit("step", {"step": {**step, "status": "done"}})
                messages.append({"role": "tool", "content": result, "tool_name": name})
            if ctx.streaming:
                await ctx.emit("token_reset", {})
        if not final.strip() and rounds >= max_rounds:
            final = f"I stopped after {max_rounds} rounds of tool calls (Max tool rounds, Agent → Advanced) before finishing."

        return Message(
            text=final,
            properties={"steps": steps, "source": {"id": ctx.node_id, "display_name": "Agent", "source": cfg.model},
                        **({"thinking": all_thinking[-4000:]} if all_thinking.strip() else {})},
        )


class Skill(Component):
    key = "Skill"
    display = "Skill"
    category = "Agents"
    description = "A pack of instructions an agent loads only when it needs it. Pick one from your library or write it here."
    icon = "sparkles"
    tool_mode = False
    fields = [
        Field("skill", "From library", "skill", "", info="Leave blank to write the skill inline."),
        Field("name", "Name", "str", "", placeholder="e.g. code-review"),
        Field("description", "When to use", "text", "", placeholder="Use when the user asks to ..."),
        Field("body", "Instructions", "text", "", placeholder="# Steps\n1. ..."),
    ]
    outputs = [Output("skill", "Skill", SKILL)]

    async def out_skill(self, ctx) -> SkillDef:
        lib = await ctx.text("skill")
        if lib:
            found = load_library_skills([lib])
            if not found:
                raise ValueError(f"Skill '{lib}' is not in your library any more.")
            return found[0]
        name = (await ctx.text("name")).strip()
        if not name:
            raise ValueError("Give the skill a name, or pick one from the library.")
        return SkillDef(name=name, description=await ctx.text("description"), body=await ctx.text("body"))
