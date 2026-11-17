"""Agent with tool calling on Ollama, plus Skills: instruction packs loaded on demand."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
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


# ---------------------------------------------------------------- built-in agent tools

PLAN_PROMPT = ("\n## Plan\nFor any task with 3 or more steps, first call update_plan with the steps. Keep it current: "
               "mark a step in_progress when you start it and done when it is finished, and add steps you discover. "
               "Keep working until every step is done.")
HELPER_PROMPT = ("\n## Helpers\nFor a self-contained side task (research a question, inspect a folder, try something out) "
                 "you can call delegate: a helper with a fresh memory does it with your tools and returns a short report. "
                 "Give it everything it needs in the task text; it can't see this conversation.")
HELPER_SYSTEM = ("You are a helper agent. Do exactly the task you're given using your tools, then reply with a concise "
                 "report (under 300 words): what you found or did, with file paths, commands and key results. "
                 "Always act with tools; never just describe what you would do.")
LEARN_PROMPT = ("\n## Learning\nWhen you finish a multi-step task the user is likely to ask for again and you found a "
                "reliable way to do it, end your answer by offering to save it as a skill. If the user agrees (now or "
                "later), call save_skill with a short kebab-case name, a 'Use when ...' description, and the step-by-step "
                "method that worked (commands, paths, gotchas). Saving asks the user to approve.")
_STATUS = {"pending": "pending", "todo": "pending", "in_progress": "in_progress", "doing": "in_progress", "active": "in_progress",
           "done": "done", "completed": "done", "complete": "done", "finished": "done"}


def normalize_plan(raw: Any) -> list[dict[str, str]]:
    """Accept the shapes small models produce: [{text|step|title, status}], ["a", "b"], or '- [x] a\\n- [ ] b'."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [ln for ln in raw.splitlines() if ln.strip()]
    if isinstance(raw, dict):
        raw = raw.get("steps") or raw.get("plan") or []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("step") or item.get("title") or item.get("description") or "").strip()
            status = _STATUS.get(str(item.get("status") or "pending").lower().replace(" ", "_"), "pending")
        else:
            line = str(item).strip()
            m = re.match(r"^[-*\d.)\s]*\[(x|X| |~|>)\]\s*(.*)$", line)
            if m:
                text, status = m.group(2), {"x": "done", "X": "done", "~": "in_progress", ">": "in_progress"}.get(m.group(1), "pending")
            else:
                text, status = re.sub(r"^[-*\d.)\s]+", "", line), "pending"
        if text:
            out.append({"text": text[:200], "status": status})
    return out[:30]


def plan_tool(state: list[dict[str, str]], emit) -> ToolDef:
    async def update_plan(a: dict[str, Any]) -> str:
        steps = normalize_plan(a.get("steps", a.get("input", a)))
        if not steps:
            return 'Give steps as a list, e.g. [{"text": "Read the config", "status": "in_progress"}, {"text": "Fix the bug", "status": "pending"}].'
        state[:] = steps
        await emit("plan", {"steps": steps})
        done = sum(s["status"] == "done" for s in steps)
        nxt = next((s["text"] for s in steps if s["status"] != "done"), None)
        return f"Plan saved ({done}/{len(steps)} done)." + (f" Next: {nxt}" if nxt else " All steps are done: give your final answer.")

    item = {"type": "object", "properties": {"text": {"type": "string"},
                                             "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}},
            "required": ["text", "status"]}
    return ToolDef("update_plan", "Write or update your step-by-step plan (the user sees it as a live checklist).",
                   {"type": "object", "properties": {"steps": {"type": "array", "items": item, "description": "All steps, in order"}},
                    "required": ["steps"]}, update_plan)


def save_skill_tool(ctx) -> ToolDef:
    async def save_skill(a: dict[str, Any]) -> str:
        name = re.sub(r"[^a-z0-9-]+", "-", str(a.get("name") or "").lower()).strip("-")[:64]
        desc = str(a.get("description") or "").strip()
        body = str(a.get("instructions") or a.get("body") or "").strip()
        if not name or not desc or not body:
            return "Give a name, a 'Use when ...' description and the step-by-step instructions."
        if not ctx.engine.interactive:
            return "Saving a skill needs the user's approval, and nobody is watching this run. Not saved."
        with db.conn() as c:
            exists = c.execute("SELECT id FROM skills WHERE name=?", (name,)).fetchone()
        ok = await ctx.engine.ask_approval(ctx.node_id, "skill", f"{'update' if exists else 'save'} skill {name}",
                                           {"name": name, "description": desc, "instructions": body[:6000]})
        if not ok:
            return "The user chose not to save this skill."
        with db.conn() as c:
            if exists:
                c.execute("UPDATE skills SET description=?, body=?, updated_at=? WHERE name=?", (desc, body, db.now(), name))
            else:
                c.execute("INSERT INTO skills(id,name,description,body,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                          (db.new_id(), name, desc, body, db.now(), db.now()))
        return f"Skill '{name}' {'updated' if exists else 'saved'} in the library (Skills page)."

    return ToolDef("save_skill", "Save a reliable method as a reusable skill in the user's library (asks the user first).",
                   {"type": "object", "properties": {
                       "name": {"type": "string", "description": "kebab-case, e.g. weekly-report"},
                       "description": {"type": "string", "description": "Use when ..."},
                       "instructions": {"type": "string", "description": "Step-by-step method in Markdown"}},
                    "required": ["name", "description", "instructions"]}, save_skill)


def startup_instructions(engine: Any, folders: list[Path]) -> str:
    """AGENTS.md from the project folder and the workspace, given to the agent up front."""
    from .power import project_instructions

    return "".join(project_instructions(engine, f) for f in folders if f.is_dir())


def attached_images(file_ids: list[str]) -> tuple[list[str], list[str]]:
    import base64

    from .. import uploads

    images, names = [], []
    for fid in file_ids:
        got = uploads.load(str(fid))
        if got and got[0].get("kind") == "image":
            images.append(base64.b64encode(got[2].read_bytes()).decode())
            names.append(got[0]["name"])
    return images, names


@dataclass
class LoopResult:
    final: str
    steps: list[dict[str, Any]]
    thinking: str
    usage: dict[str, Any]
    rounds: int


COMPACT_AT = 0.8  # share of the context window that triggers summarizing


async def agent_loop(ctx, cfg, messages: list[dict[str, Any]], tools: list[ToolDef], *, max_rounds: int, think: bool | None,
                     top: bool, keep_from: int, auto_compact: bool = True, label: str = "") -> LoopResult:
    """The tool-calling loop. `top` = the agent the user is chatting with (streams to the chat);
    helpers run the same loop quietly. messages[keep_from] is the current task: it is never summarized."""
    by_name = {t.name: t for t in tools}
    ctx_limit = int(cfg.options.get("num_ctx") or OLLAMA_DEFAULT_CTX)
    steps: list[dict[str, Any]] = []
    final, all_thinking = "", ""
    rounds = nudges = 0
    warned = False
    usage: dict[str, Any] = {"limit": ctx_limit}
    prefix = f"{label} › " if label else ""
    while True:
        offer = bool(tools) and rounds < max_rounds
        used, trimmed = fit_context(messages, ctx_limit)
        if usage.get("used"):
            used = max(used, int(usage["used"]))
        if auto_compact and used > COMPACT_AT * ctx_limit:
            if top:
                await ctx.emit("status", {"text": "Summarizing earlier steps to free up the model's memory…"})
            done = await compact_loop(ctx, cfg, messages, keep_from, top)
            if done:
                keep_from = done
                used, _ = fit_context(messages, ctx_limit)
                usage.pop("used", None)
        if top and (trimmed or used > 0.85 * ctx_limit) and not warned:
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
                if top and ctx.streaming:
                    await ctx.emit("thinking", {"chunk": th})
            tok = m.get("content") or ""
            if tok:
                content += tok
                if top and ctx.streaming:
                    await ctx.emit("token", {"chunk": tok})
            calls += m.get("tool_calls") or []
            if ch.get("done"):
                pe, ev, ed = ch.get("prompt_eval_count"), ch.get("eval_count"), ch.get("eval_duration")
                if pe is not None or ev is not None:
                    usage["used"] = int(pe or 0) + int(ev or 0)
                    usage["output_tokens"] = usage.get("output_tokens", 0) + int(ev or 0)
                    if ev and ed:
                        usage["tokens_per_sec"] = round(ev / (ed / 1e9), 1)
                    if top:
                        await ctx.emit("usage", dict(usage))
        if not calls and offer:
            calls, content = parse_text_tool_calls(content, by_name)  # tool calls the model wrote out as text
        if not calls:
            if offer and nudges < MAX_NUDGES and looks_unfinished(content):
                # It said what it would do (or said nothing) but called no tool: remind it, don't stop.
                nudges += 1
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": NUDGE})
                if top:
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
            step: dict[str, Any] = {"type": "tool", "name": prefix + name, "input": args}
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
        if top and ctx.streaming:
            await ctx.emit("token_reset", {})
    if not final.strip() and rounds >= max_rounds:
        final = f"I stopped after {max_rounds} rounds of tool calls (Max tool rounds, Agent → Advanced) before finishing."
    return LoopResult(final, steps, all_thinking, usage, rounds)


async def compact_loop(ctx, cfg, messages: list[dict[str, Any]], keep_from: int, top: bool) -> int | None:
    """Summarize what came before the current task (chat memory) and, if still needed, the older steps of
    this task, keeping the system prompt, the task and the last 4 messages. Returns the task's new index."""
    from .. import compact

    changed = None
    # 1. earlier chat (persisted, so the next message starts from the summary too)
    if keep_from > 2:
        older = messages[1:keep_from]
        text = await compact.summarize(cfg.base_url, cfg.model, older, cfg.options)
        if top and ctx.engine.persist:
            covers = getattr(ctx.engine, "_history_last", None)
            if covers:
                compact.store_summary(ctx.engine.flow_id, ctx.session_id, text, covers, len(older))
        messages[1:keep_from] = [{"role": "user", "content": f"[Summary of our earlier conversation]\n{text}"}]
        keep_from = 2
        changed = keep_from
        if estimate_tokens(messages) <= COMPACT_AT * int(cfg.options.get("num_ctx") or OLLAMA_DEFAULT_CTX) * 0.9:
            return changed
    # 2. older steps of the current task
    tail_start = len(messages) - 4
    while tail_start > keep_from + 1 and messages[tail_start].get("role") != "assistant":
        tail_start -= 1
    if tail_start - (keep_from + 1) >= 2:
        middle = messages[keep_from + 1:tail_start]
        text = await compact.summarize(cfg.base_url, cfg.model, middle, cfg.options)
        messages[keep_from + 1:tail_start] = [{"role": "user", "content": f"[Progress so far on this task, summarized to save memory]\n{text}"}]
        changed = keep_from
    return changed


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
        Field("plan", "Plan checklist", "bool", False,
              info="The agent writes a step-by-step plan you see live in the chat, and ticks steps off. Keeps long tasks on track."),
        Field("sub_agents", "Helpers (sub-agents)", "bool", False,
              info="The agent can hand a side task to a helper with a fresh memory (delegate). Saves memory on big jobs."),
        Field("learn_skills", "Learn skills", "bool", False,
              info="After a task that's likely to come back, the agent offers to save its method as a skill. Saving asks you."),
        Field("project_folder", "Project folder", "str", "", placeholder="C:\\Users\\you\\code\\my-app",
              info="Optional. Its AGENTS.md is read at the start. AGENTS.md files in folders the agent opens are read too."),
        Field("memory", "Chat memory", "bool", True, advanced=True, info="Include this session's earlier messages."),
        Field("n_messages", "Messages to remember", "int", 20, advanced=True),
        Field("auto_compact", "Summarize when memory fills", "bool", True, advanced=True,
              info="Near the context window limit, older messages and steps are summarized instead of dropped."),
        Field("max_iterations", "Max tool rounds", "int", 20, advanced=True,
              info="How many rounds of tool calls before the agent must answer. Each round can call several tools."),
    ]
    outputs = [Output("response", "Response", MESSAGE)]

    async def out_response(self, ctx) -> Message:
        cfg = await llm_from_ctx(ctx, "llm")
        task = await ctx.text("input")
        system = await ctx.text("system_prompt") or DEFAULT_INSTRUCTIONS
        is_top_level = not ctx.overrides  # a tool-call run of a sub-agent gets no chat memory

        skills: list[SkillDef] = [s for s in await ctx.get("skills", []) if isinstance(s, SkillDef)]
        skills += [s for s in load_library_skills(await ctx.get("library_skills")) if s.name not in {x.name for x in skills}]
        tools: list[ToolDef] = [t for t in await ctx.get("tools", []) if isinstance(t, ToolDef)]
        base_tools = list(tools)  # what helpers get
        if skills:
            system += "\n" + skills_prompt(skills)
            tools.append(skill_tool(skills))
        if await ctx.get("long_term_memory", False) and is_top_level:
            from .. import memory as ltm

            system += "\n" + ltm.prompt_block()
            tools += memory_tools()
        plan_state: list[dict[str, str]] = []
        if await ctx.get("plan", False):
            system += PLAN_PROMPT
            tools.append(plan_tool(plan_state, ctx.emit))
        max_rounds = max(1, int(await ctx.get("max_iterations", 20)))
        think = True if await ctx.get("think", False) else None
        auto_compact = bool(await ctx.get("auto_compact", True))
        if await ctx.get("sub_agents", False) and base_tools:
            system += HELPER_PROMPT
            tools.append(self._delegate_tool(ctx, cfg, base_tools, max_rounds, think, auto_compact))
        if await ctx.get("learn_skills", False) and is_top_level:
            system += LEARN_PROMPT
            tools.append(save_skill_tool(ctx))
        if is_top_level:
            from .power import default_workspace

            folders = [Path(p).expanduser() for p in [await ctx.text("project_folder")] if p.strip()] + [default_workspace()]
            system += startup_instructions(ctx.engine, folders)
        tools = _dedupe(tools)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if is_top_level and await ctx.get("memory", True):
            hist = ctx.engine.history(ctx.session_id, int(await ctx.get("n_messages", 20)))
            for m in hist:
                if m.get("summary"):
                    messages.append({"role": "user", "content": f"[Summary of our earlier conversation]\n{m['text']}"})
                else:
                    messages.append({"role": "user" if m["sender"] == "user" else "assistant", "content": m["text"]})
            ctx.engine._history_last = hist[-1]["created_at"] if hist else None
        user_msg: dict[str, Any] = {"role": "user", "content": task}
        if is_top_level and ctx.engine.files:
            images, names = attached_images(ctx.engine.files)
            if images:
                caps = await ollama.capabilities(cfg.base_url, cfg.model)
                if caps is not None and "vision" not in caps:
                    user_msg["content"] += (f"\n\n(The user attached {', '.join(names)}, but this model can't see images. "
                                            "Say so, and suggest a vision model such as qwen2.5vl or gemma3.)")
                else:
                    user_msg["images"] = images
        messages.append(user_msg)

        res = await agent_loop(ctx, cfg, messages, tools, max_rounds=max_rounds, think=think, top=is_top_level,
                               keep_from=len(messages) - 1, auto_compact=auto_compact)
        props: dict[str, Any] = {"steps": res.steps, "source": {"id": ctx.node_id, "display_name": "Agent", "source": cfg.model}}
        if res.thinking.strip():
            props["thinking"] = res.thinking[-4000:]
        if plan_state:
            props["plan"] = plan_state
        if res.usage.get("used") or res.usage.get("tokens_per_sec"):
            props["usage"] = res.usage
        if is_top_level and ctx.engine.changed_files and ctx.engine.run_id:
            props["changes"] = {"run_id": ctx.engine.run_id, "files": list(ctx.engine.changed_files)}
        return Message(text=res.final, properties=props)

    def _delegate_tool(self, ctx, cfg, base_tools: list[ToolDef], max_rounds: int, think: bool | None, auto_compact: bool) -> ToolDef:
        async def delegate(a: dict[str, Any]) -> str:
            job = str(a.get("task") or a.get("input") or "").strip()
            if not job:
                return "Describe the task for the helper."
            extra = str(a.get("context") or "").strip()
            await ctx.emit("status", {"text": f"A helper is working on: {job[:120]}"})
            msgs = [{"role": "system", "content": HELPER_SYSTEM},
                    {"role": "user", "content": job + (f"\n\nContext:\n{extra}" if extra else "")}]
            res = await agent_loop(ctx, cfg, msgs, _dedupe(list(base_tools)), max_rounds=min(max_rounds, 15), think=think,
                                   top=False, keep_from=1, auto_compact=auto_compact, label="helper")
            report = res.final.strip() or "The helper finished without a report."
            return f"Helper report ({res.rounds} tool rounds):\n{report[:6000]}"

        return ToolDef("delegate", "Hand a self-contained side task to a helper agent with a fresh memory and your tools; "
                       "returns its report. Include all needed details in the task.",
                       {"type": "object", "properties": {
                           "task": {"type": "string", "description": "What the helper should do and report back"},
                           "context": {"type": "string", "description": "Optional facts it needs (paths, findings)"}},
                        "required": ["task"]}, delegate)


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
