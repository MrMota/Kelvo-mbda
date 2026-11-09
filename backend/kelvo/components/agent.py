"""Agent with tool calling on Ollama, plus Skills: instruction packs loaded on demand."""
from __future__ import annotations

import json
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
        Field("memory", "Chat memory", "bool", True, advanced=True, info="Include this session's earlier messages."),
        Field("n_messages", "Messages to remember", "int", 20, advanced=True),
        Field("max_iterations", "Max tool rounds", "int", 8, advanced=True),
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
        tools = _dedupe(tools)
        by_name = {t.name: t for t in tools}

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        is_top_level = not ctx.overrides  # a tool-call run of a sub-agent gets no chat memory
        if is_top_level and await ctx.get("memory", True):
            for m in ctx.engine.history(ctx.session_id, int(await ctx.get("n_messages", 20))):
                messages.append({"role": "user" if m["sender"] == "user" else "assistant", "content": m["text"]})
        messages.append({"role": "user", "content": task})

        steps: list[dict[str, Any]] = []
        max_rounds = max(1, int(await ctx.get("max_iterations", 8)))
        final = ""
        think = True if await ctx.get("think", False) else None
        for round_no in range(max_rounds + 1):
            content, calls = "", []
            offer_tools = [t.schema() for t in tools] if tools and round_no < max_rounds else None
            async for ch in ollama.chat_stream(cfg.base_url, cfg.model, messages, tools=offer_tools,
                                               options=cfg.options, keep_alive=cfg.keep_alive, think=think):
                m = ch.get("message") or {}
                tok = m.get("content") or ""
                if tok:
                    content += tok
                    if ctx.streaming:
                        await ctx.emit("token", {"chunk": tok})
                calls += m.get("tool_calls") or []
            if not calls:
                final = content
                break
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
        else:
            final = final or "I stopped after reaching the maximum number of tool rounds."

        return Message(
            text=final,
            properties={"steps": steps, "source": {"id": ctx.node_id, "display_name": "Agent", "source": cfg.model}},
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
