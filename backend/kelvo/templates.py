"""Starter flows. Models are left blank so they use the default model from Settings."""
from __future__ import annotations

from typing import Any


def _n(id: str, type_: str, x: int, y: int, params: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"id": id, "type": "component", "position": {"x": x, "y": y},
            "data": {"type": type_, "params": params or {}, **extra}}


def _e(src: str, out: str, dst: str, field: str) -> dict[str, Any]:
    return {"id": f"e-{src}-{out}-{dst}-{field}", "source": src, "sourceHandle": out, "target": dst, "targetHandle": field}


def _note(id: str, x: int, y: int, text: str) -> dict[str, Any]:
    return {"id": id, "type": "note", "position": {"x": x, "y": y}, "data": {"text": text}}


TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "basic-prompting",
        "name": "Basic Prompting",
        "description": "Chat Input → Prompt → Ollama → Chat Output. The smallest useful flow.",
        "icon": "braces",
        "data": {
            "nodes": [
                _n("chat_in", "ChatInput", 0, 160),
                _n("prompt", "Prompt", 380, 60, {"template": "You are a friendly expert. Answer in a few sentences.\n\nQuestion: {question}"}),
                _n("llm", "OllamaModel", 760, 0),
                _n("chat_out", "ChatOutput", 1140, 160),
            ],
            "edges": [
                _e("chat_in", "message", "prompt", "question"),
                _e("prompt", "prompt", "llm", "input"),
                _e("llm", "response", "chat_out", "input"),
            ],
        },
    },
    {
        "id": "simple-agent",
        "name": "Simple Agent",
        "description": "An agent with a calculator, the current date and a URL reader as tools.",
        "icon": "bot",
        "data": {
            "nodes": [
                _n("chat_in", "ChatInput", 0, 300),
                _n("calc", "Calculator", 0, -280, tool_mode=True),
                _n("date", "CurrentDate", 0, 10, tool_mode=True),
                _n("url", "URLFetch", 0, 660, tool_mode=True),
                _n("agent", "Agent", 420, 40),
                _n("chat_out", "ChatOutput", 820, 260),
                _note("note", 420, -150, "Pick a tool-capable model in the Agent (llama3.1, qwen2.5, qwen3, mistral-nemo), then open the Playground."),
            ],
            "edges": [
                _e("chat_in", "message", "agent", "input"),
                _e("calc", "tool", "agent", "tools"),
                _e("date", "tool", "agent", "tools"),
                _e("url", "tool", "agent", "tools"),
                _e("agent", "response", "chat_out", "input"),
            ],
        },
    },
    {
        "id": "power-agent",
        "name": "Power Agent",
        "description": "Searches the web, reads pages, writes and edits files, and runs commands (you approve each one).",
        "icon": "terminal",
        "data": {
            "nodes": [
                _n("chat_in", "ChatInput", 0, 880),
                _n("search", "WebSearch", 0, -600, tool_mode=True),
                _n("url", "URLFetch", 0, -280, tool_mode=True),
                _n("files", "Files", 0, 20, tool_mode=True),
                _n("shell", "Shell", 0, 380, tool_mode=True),
                _n("calc", "Calculator", 0, 1180, tool_mode=True),
                _n("agent", "Agent", 460, 120, {
                    "system_prompt": (
                        "You are a capable assistant working on the user's own computer.\n"
                        "- For anything current or factual you're unsure of: web_search, then read the best 1-3 results with the url tool. Cite the URLs you used.\n"
                        "- Work with files only through list_files, read_file, write_file and edit_file, inside the workspace. Read a file before editing it; keep edits small and exact.\n"
                        "- Use the command line for things only a command can do (running code, git, converting files). Say in one line why before each command; the user approves it.\n"
                        "- Plan briefly, do the work, then answer clearly and say what you changed."
                    ),
                    "think": True,
                    "library_skills": ["*"],
                    "num_ctx": 16384,
                    "max_iterations": 15,
                }),
                _n("chat_out", "ChatOutput", 880, 380),
                _note("note", 460, -120, "Pick a model marked 'tools' (qwen3:30b on a big GPU). Files and commands stay in your KelvoWorkspace folder; every command waits for your Approve in the Playground."),
            ],
            "edges": [
                _e("chat_in", "message", "agent", "input"),
                _e("search", "tool", "agent", "tools"),
                _e("url", "tool", "agent", "tools"),
                _e("files", "tool", "agent", "tools"),
                _e("shell", "tool", "agent", "tools"),
                _e("calc", "tool", "agent", "tools"),
                _e("agent", "response", "chat_out", "input"),
            ],
        },
    },
    {
        "id": "skilled-agent",
        "name": "Skilled Agent",
        "description": "An agent that loads skills only when a request needs them.",
        "icon": "sparkles",
        "data": {
            "nodes": [
                _n("chat_in", "ChatInput", 0, 60),
                _n("skill_email", "Skill", -400, -320, {
                    "name": "email-writer",
                    "description": "Use when the user asks to write, reply to or polish an email.",
                    "body": "1. Ask nothing; infer tone from the request.\n2. Write a subject line, then the email.\n3. Keep it under 150 words, plain words, one clear ask.\n4. End with a short sign-off and [Name].",
                }),
                _n("skill_plan", "Skill", -400, 230, {
                    "name": "step-planner",
                    "description": "Use when the user wants a plan, checklist or steps to reach a goal.",
                    "body": "Return a numbered plan of 3–7 steps. Each step starts with a verb and has a 'done when' line. Finish with the single riskiest step.",
                }),
                _n("calc", "Calculator", 0, 340, tool_mode=True),
                _n("agent", "Agent", 420, 0, {"library_skills": ["*"]}),
                _n("chat_out", "ChatOutput", 820, 220),
                _note("note", 420, -170, "Skills stay out of the context until the agent calls load_skill. Edit library skills on the Skills page."),
            ],
            "edges": [
                _e("chat_in", "message", "agent", "input"),
                _e("skill_email", "skill", "agent", "skills"),
                _e("skill_plan", "skill", "agent", "skills"),
                _e("calc", "tool", "agent", "tools"),
                _e("agent", "response", "chat_out", "input"),
            ],
        },
    },
    {
        "id": "multi-agent",
        "name": "Multi-Agent Team",
        "description": "A lead agent delegates research to a sub-agent used as a tool.",
        "icon": "users",
        "data": {
            "nodes": [
                _n("chat_in", "ChatInput", 400, 520),
                _n("url", "URLFetch", 0, -200, tool_mode=True),
                _n("researcher", "Agent", 400, -420, {
                    "system_prompt": "You are a meticulous researcher. Fetch sources with your tools and return concise findings with the URLs you used.",
                    "memory": False,
                }, tool_mode=True, tool_name="researcher", tool_description="Delegate a research question; returns findings with sources.", display_name="Researcher"),
                _n("calc", "Calculator", 400, 200, tool_mode=True),
                _n("lead", "Agent", 820, 0, {
                    "system_prompt": "You are the team lead. Break the request down, delegate research to the researcher tool, use the calculator for numbers, then write the final answer.",
                }, display_name="Lead Agent"),
                _n("chat_out", "ChatOutput", 1220, 220),
            ],
            "edges": [
                _e("url", "tool", "researcher", "tools"),
                _e("researcher", "tool", "lead", "tools"),
                _e("calc", "tool", "lead", "tools"),
                _e("chat_in", "message", "lead", "input"),
                _e("lead", "response", "chat_out", "input"),
            ],
        },
    },
    {
        "id": "document-qa",
        "name": "Document Q&A (local RAG)",
        "description": "Embed a document with Ollama, store it locally, and answer questions from it.",
        "icon": "database",
        "data": {
            "nodes": [
                _n("doc", "TextInput", 0, -100, {"value": "Paste your document here. Kelvo splits it into chunks, embeds each with an Ollama embedding model, and keeps the vectors in its own database."}, display_name="Document"),
                _n("split", "SplitText", 380, -160, {"chunk_size": 800, "overlap": 100}),
                _n("emb", "OllamaEmbeddings", 380, 220),
                _n("chat_in", "ChatInput", 0, 420),
                _n("kb", "KnowledgeBase", 760, 0, {"collection": "docs"}),
                _n("prompt", "Prompt", 1140, 160, {"template": "Answer using only the context. If the answer is not there, say so.\n\nContext:\n{context}\n\nQuestion: {question}"}),
                _n("llm", "OllamaModel", 1520, 60),
                _n("chat_out", "ChatOutput", 1900, 220),
            ],
            "edges": [
                _e("doc", "text", "split", "input"),
                _e("split", "chunks", "kb", "ingest"),
                _e("emb", "embeddings", "kb", "embedding"),
                _e("chat_in", "message", "kb", "query"),
                _e("kb", "context", "prompt", "context"),
                _e("chat_in", "message", "prompt", "question"),
                _e("prompt", "prompt", "llm", "input"),
                _e("llm", "response", "chat_out", "input"),
            ],
        },
    },
    {
        "id": "structured-extraction",
        "name": "Structured Extraction",
        "description": "Turn free text into JSON with a schema, then format it.",
        "icon": "table",
        "data": {
            "nodes": [
                _n("chat_in", "ChatInput", 0, 120),
                _n("extract", "StructuredOutput", 380, 0, {
                    "instructions": "Extract the contact details mentioned in the text.",
                    "schema": '{\n  "type": "object",\n  "properties": {\n    "name": {"type": "string"},\n    "email": {"type": "string"},\n    "company": {"type": "string"}\n  },\n  "required": ["name"]\n}',
                }),
                _n("parse", "Parser", 760, 60, {"template": "Name: {name}\nEmail: {email}\nCompany: {company}"}),
                _n("chat_out", "ChatOutput", 1140, 120),
            ],
            "edges": [
                _e("chat_in", "message", "extract", "input"),
                _e("extract", "data", "parse", "input"),
                _e("parse", "text", "chat_out", "input"),
            ],
        },
    },
]

STARTER_SKILLS = [
    {
        "name": "summarize",
        "description": "Use when the user asks to summarise, condense or give the gist of a text or page.",
        "body": "# Summarize\n\n1. Read the whole input first.\n2. Lead with a one-sentence takeaway.\n3. Then 3–5 bullets, most important first, each under 20 words.\n4. Keep names, numbers and dates exact. Never invent facts.\n5. If the text is opinion, say whose opinion it is.",
    },
    {
        "name": "code-review",
        "description": "Use when the user shares code and asks for a review, bugs or improvements.",
        "body": "# Code review\n\nCheck in this order and report only real issues:\n1. **Correctness**: wrong logic, off-by-one, unhandled None/null, race conditions.\n2. **Security**: injection, secrets in code, unsafe input handling.\n3. **Clarity**: naming, dead code, functions doing too much.\n\nFor each issue give: line or snippet, why it is wrong, a fixed version. End with a one-line verdict.",
    },
    {
        "name": "sql-helper",
        "description": "Use when the user wants an SQL query written, explained or optimised.",
        "body": "# SQL helper\n\n- Ask which dialect only if it changes the answer; default to PostgreSQL.\n- Write the query in a ```sql block, keywords uppercase, one clause per line.\n- Explain it in 2–4 bullets.\n- Mention the index that would make it fast.\n- Never write DELETE/UPDATE without a WHERE clause.",
    },
]
