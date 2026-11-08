# Kelvo

A visual builder for AI agents, tools and skills that runs **entirely on open models through [Ollama](https://ollama.com)**.
Drag components onto a canvas, wire them together, chat with the result in the Playground, then call it from your
apps over a REST API or from any MCP client.

- **Agents** that call tools in a loop (any component can be switched into *tool mode*), with chat memory and multi-agent delegation (an agent can be another agent's tool).
- **Skills**: packs of instructions an agent loads only when it needs them. The agent sees each skill's name and description; the body enters its context when it calls `load_skill`. Small local models stay fast and focused. Skills use the `SKILL.md` format (front matter + markdown) and can be imported and exported.
- **Ollama everywhere**: chat models, embeddings, structured JSON output, model pulling from the UI. No paid API keys.
- **Local RAG**: split text, embed it with an Ollama embedding model, and search it in Kelvo's own database.
- **Run API** (`POST /api/v1/run/{flow}`) with sessions, runtime *tweaks*, and token streaming; **MCP server** (`/mcp`) exposes chosen flows as tools.
- Global variables (`${NAME}` in any field), API keys, run logs, import/export, light and dark themes.
- **Just for you**: one username/password account, no sign-up, no other users.

## Quick start

You need [Ollama](https://ollama.com/download) running with at least one model:

```bash
ollama pull qwen3:8b            # or llama3.1:8b — agents need a tool-capable model
ollama pull nomic-embed-text    # for the Document Q&A template
```

Running it on your own server (private access, backups, updates): see **`replica/deploy.md`**.

Then either **Docker** (bundles Ollama too):

```bash
cp .env.example .env            # account + NVIDIA GPU switch (delete the COMPOSE_FILE line without one)
docker compose up -d --build    # → http://127.0.0.1:7860
docker compose exec ollama ollama pull qwen3:8b
```

or **from source** (Python 3.10+, Node 20+):

```bash
make install
make run                        # → http://127.0.0.1:7860
```

**Sign in.** Kelvo has exactly one account: yours. There is no sign-up. Create it one of three ways:

- set `KELVO_USERNAME` and `KELVO_PASSWORD` before the first start (Docker: put them in a `.env` file next to `docker-compose.yml`), or
- open the app and enter the one-time **setup token** printed in the server log, or
- run `kelvo set-password` on the server (also how you reset a forgotten password).

Then open **Settings → Models**, check the Ollama URL, and pick a **default model**: every template uses it. Then **New Flow → Simple Agent → Playground**.

No GPU at hand? `make fake-ollama` starts a stand-in Ollama on port 11435 that echoes and calls tools on cue, which is what the tests use.

## Components

| Category | Components |
| --- | --- |
| Input & Output | Chat Input, Chat Output, Text Input, Text Output |
| Prompts | Prompt Template (each `{variable}` becomes an input port) |
| Models | Ollama, Ollama Embeddings, Structured Output |
| Agents | Agent, Skill |
| Tools | Calculator, Current Date, URL, Run Flow |
| Memory | Message History |
| Vector Stores | Knowledge Base (local) |
| Processing | Parser, Split Text |
| Logic | If-Else |

Ports are typed (Message, Text, Data, LanguageModel, Embeddings, Tool, Skill) and colour-coded; the canvas refuses connections that don't fit.
Click the wrench on a component to put it in **tool mode**: its *Toolset* output plugs into an Agent's *Tools* port, and the fields marked "filled by agent" become the tool's arguments.

## Templates

Basic Prompting · Simple Agent · Skilled Agent · Multi-Agent Team · Document Q&A (local RAG) · Structured Extraction

## Calling a flow

Create a key in **Settings → API keys**, then:

```bash
curl -X POST http://127.0.0.1:7860/api/v1/run/<flow-id-or-endpoint-name> \
  -H "Content-Type: application/json" -H "x-api-key: $KELVO_API_KEY" \
  -d '{"input_value": "Hello!", "session_id": "user-1",
       "tweaks": {"<node-id>": {"temperature": 0.7}}}'
```

Add `?stream=true` for server-sent events (`token`, `step`, `message`, `end`). **Share → API access** in the editor generates cURL, Python and JavaScript snippets.

## MCP

In **Share → MCP server**, expose a flow as a tool and give it a clear name and description. Point any MCP client at the Streamable HTTP endpoint:

```json
{ "mcpServers": { "kelvo": { "type": "http", "url": "http://127.0.0.1:7860/mcp",
                                "headers": { "x-api-key": "YOUR_KEY" } } } }
```

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | used until set in Settings |
| `KELVO_DB` | `~/.kelvo/kelvo.db` | SQLite file |
| `KELVO_HOST` / `KELVO_PORT` | `127.0.0.1` / `7860` | |
| `KELVO_USERNAME` / `KELVO_PASSWORD` | — | create your account on first start (ignored once it exists) |
| `KELVO_SESSION_DAYS` | `30` | how long a sign-in lasts |
| `KELVO_SECURE_COOKIE` | `0` | `1` marks the session cookie Secure (set it when you serve Kelvo over HTTPS) |
| `KELVO_REQUIRE_API_KEY` | `1` | `0` disables keys on `/api/v1/run` and `/mcp` (local use only) |
| `KELVO_ALLOW_PRIVATE_URLS` | `0` | let the URL tool fetch private-network addresses |
| `KELVO_OLLAMA_TIMEOUT` | `600` | seconds per model call |

**Security.** The editor and its API need your sign-in (scrypt-hashed password, HttpOnly SameSite cookie, cross-site writes refused, 5 failed sign-ins lock that address for 60 s). The run API and MCP server need an API key instead. Kelvo binds to `127.0.0.1` by default; to reach it from your other devices, run it with `--host 0.0.0.0` on a private network or VPN (e.g. Tailscale), not on the open internet, and set `KELVO_SECURE_COOKIE=1` if you put HTTPS in front of it.

## Development

```
backend/kelvo/
  engine.py          lazy, pull-based graph runner; tool mode; events
  components/        the registry: one class per component, served to the UI at /api/components
  main.py            REST API, run API, SSE
  mcp.py             MCP server (JSON-RPC over HTTP)
  ollama.py          Ollama client
  fake_ollama.py     stand-in Ollama for tests
frontend/src/        React + React Flow editor
e2e/smoke.mjs        Playwright click-through of the core flows
replica/             recon map, architecture, schema, feature matrix, test plan
```

```bash
make test            # backend tests
make dev-backend     # API on :7860 with reload
make dev-frontend    # UI on :5173
make e2e             # browser click-through against a running server
```

To add a component, subclass `Component` in `backend/kelvo/components/`, declare `fields` and `outputs`, write an `out_<name>` coroutine per output, and add it to `ALL`. The UI picks it up from the registry; no frontend change is needed.

## License

MIT
