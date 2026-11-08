# Architecture: MBDAflow

## Stack

| layer | choice | why |
| --- | --- | --- |
| backend | Python 3.11+ / FastAPI / uvicorn | agent runtimes live in Python; async streaming (SSE) is first-class |
| LLM | Ollama HTTP API (`/api/chat`, `/api/tags`, `/api/embed`, `/api/pull`) via httpx | the brief: open models only, local or remote Ollama |
| database | SQLite (stdlib `sqlite3`, raw SQL, WAL) | self-hosted single binary feel; zero setup; swap to Postgres later |
| frontend | React 18 + TypeScript + Vite | standard, fast |
| canvas | @xyflow/react (React Flow) | the de-facto MIT node editor; typed handles, minimap, zoom |
| styling | plain CSS with design tokens (CSS variables) | no build plugin, light + dark |
| auth | none for the local UI; API keys (sha256-hashed) for `/api/v1/run` and `/mcp` | single-owner self-hosted tool, like the original's local mode |
| hosting | one process: FastAPI serves the built SPA from `frontend/dist` | `pip install` + `mbdaflow run`, or Docker |

Deviation from the pack's default (Next.js + Postgres + Vercel): this is a self-hosted dev tool talking to a local model server, not a SaaS. One process and one SQLite file beat three managed services.

## Schema

See `schema.sql`: 9 tables (projects, flows, messages, variables, api_keys, runs, skills, vector_chunks, settings). Flow graphs are JSON in `flows.data` — they are always loaded and saved whole.

## Engine

- **Component registry** (`backend/mbdaflow/components/`): each component declares `inputs` (fields + typed handles), `outputs` (typed), and an async `run(ctx)`. The registry is served at `GET /api/components` and drives the sidebar, the node UI and edge validation — one source of truth.
- **Data types**: `Message`, `Text`, `Data`, `LanguageModel`, `Embeddings`, `Tool`, `Skill`, `VectorStore`. Edges are valid when output type ∈ input's accepted types.
- **Graph run**: topological order from the output nodes backwards; each node runs once; outputs cached per run. Cycles rejected on save and on run.
- **Tool mode**: any node with `tool_mode` exposes a `Tool` output. Calling the tool runs that node with the agent's arguments mapped onto its tool-able fields.
- **Agent**: Ollama `/api/chat` with `tools`; loop up to `max_iterations`; each tool call → step event. Skills connected to the agent are listed (name + description) in the system prompt and a `load_skill(name)` tool returns the body — progressive disclosure, so small open models keep a small context.
- **Events**: the runner emits `node_start`, `node_end`, `token`, `step` (tool call / result), `message`, `error`, `end` — streamed over SSE to the Playground and to `stream=true` API callers.

## API

| method path | what | who | input | output | flow |
| --- | --- | --- | --- | --- | --- |
| GET /api/health | liveness + ollama reachability | anyone | | {ok, ollama} | |
| GET /api/components | registry | UI | | component specs | F02 |
| GET/POST /api/projects | list/create projects | UI | {name} | project | F08 |
| GET /api/flows | list flows | UI | ?project_id | flows | F08 |
| POST /api/flows | create (blank / template / import) | UI | {name, data?, template?} | flow | F01 F02 F08 |
| GET/PATCH/DELETE /api/flows/{id} | read/update/delete | UI | partial flow | flow | F02 F08 |
| POST /api/flows/{id}/duplicate | copy | UI | | flow | F08 |
| GET /api/templates | starter templates | UI | | list | F01 |
| POST /api/flows/{id}/build | run from the editor (SSE) | UI | {input_value, session_id} | event stream | F01–F04 |
| GET /api/flows/{id}/sessions | playground sessions | UI | | [{session_id, count, last}] | F01 |
| GET/DELETE /api/flows/{id}/messages | messages of a session | UI | ?session_id | messages | F01 |
| DELETE /api/messages/{id} | edit memory | UI | | | F01 |
| GET /api/flows/{id}/runs | logs | UI | | runs | |
| POST /api/v1/run/{flow_id_or_endpoint} | run flow | API key | {input_value, input_type, output_type, session_id, tweaks, stream} | {session_id, outputs[]} or SSE | F05 |
| POST /mcp | MCP JSON-RPC (initialize, tools/list, tools/call) | API key | JSON-RPC | JSON-RPC | F06 |
| GET/POST/PATCH/DELETE /api/skills[/{id}] | skills CRUD | UI | {name, description, body} | skill | F04 |
| POST /api/skills/import | import SKILL.md | UI | {content} | skill | F04 |
| GET /api/skills/{id}/export | SKILL.md | UI | | text | F04 |
| GET/POST/PATCH/DELETE /api/variables[/{id}] | global variables | UI | | credential values masked | |
| GET/POST/DELETE /api/api-keys[/{id}] | API keys | UI | {name} | key once | F05 |
| GET/PUT /api/settings | ollama_base_url, default_model | UI | | | |
| GET /api/ollama/models | proxy `/api/tags` | UI | ?base_url | models | F01 |
| POST /api/ollama/pull | pull a model (SSE progress) | UI | {model} | stream | |

No webhooks or background jobs in v1.

## Parts that bite

- **Tool calling on open models**: not every Ollama model supports tools (Ollama returns 400). Surface the error clearly and suggest tool-capable models (llama3.1+, qwen2.5/3, mistral-nemo).
- **Long generations**: local models are slow; every model call streams and has a configurable timeout.
- **Arbitrary code**: no Python-code component; URL fetch blocks private/loopback addresses (SSRF).
- **Credentials**: credential variables are never returned to the UI in full, only `••••`.
- **Concurrency**: SQLite WAL + short transactions; one process.
- **Agent loops**: hard cap on iterations; tool errors are returned to the model as text, not raised.

## Build order

1. **Vertical slice**: registry + engine + Chat Input → Ollama → Chat Output; editor canvas; Playground streaming. (S01 S03 S04 S05 S06; flows, messages)
2. **Must-haves**: Agent + tool mode + Calculator; Skills (S13 S14) + Skill component; Prompt template; message history; templates (S02); run API + API keys + API access modal (S07 S12); global variables + model settings (S10 S11); import/export (S08).
3. **Should**: Current date, URL fetch, Run Flow, Structured output, Parser, If-Else, Split text, local vector store + Ollama embeddings, logs (S15), MCP server (S09), endpoint alias, tweaks.
4. **Could**: version history, embed widget, MCP client, human approval.
