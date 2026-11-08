# Recon map: Langflow → MBDAflow

## Scope

| | |
| --- | --- |
| App | Langflow (langflow.org), the open-source visual builder for AI agents and workflows |
| Platform | Web app (self-hosted, single user to start) |
| Slice | The core loop: **build a flow on a canvas → test it in the Playground → call it over the API/MCP**. Agents, tools, prompts, memory and local RAG are in. |
| Who it is for | The repo owner's own product: an **Ollama-only** agent builder. Every model call goes to a local or remote Ollama server running open models (Llama, Qwen, Mistral, Gemma, etc.). No paid-API providers. |
| Addition | **Skills**: reusable instruction packs (SKILL.md style: name, description, markdown body) that an agent loads only when it needs one. Langflow does not have these. |

Clean-room rule: this map comes from Langflow's **public documentation**. No source code, bundles or private APIs were read. langflow.org and docs.langflow.org are blocked from this sandbox, so the docs were read from their public markdown in the project's GitHub `docs/` folder.

## Sources

| source | URL | used for |
| --- | --- | --- |
| README | https://github.com/langflow-ai/langflow/blob/main/README.md | positioning, highlight features |
| Visual editor | https://docs.langflow.org/concepts-overview | workspace, gestures, share menu |
| Flows & projects | https://docs.langflow.org/concepts-flows | projects page, create/duplicate/lock/move/delete, version history |
| Playground | https://docs.langflow.org/concepts-playground | chat testing, tool-call display, sessions, message logs |
| Agents | https://docs.langflow.org/agents | agent params, tool mode, memory |
| Agent tools | https://docs.langflow.org/agents-tools | tool actions, approval, agent-as-tool, flows-as-tools |
| Ollama bundle | https://docs.langflow.org/bundles-ollama | base URL, model refresh, LanguageModel output, embeddings |
| Publish | https://docs.langflow.org/concepts-publish | API access snippets, tweaks, endpoint alias, embed widget |
| Run API | https://docs.langflow.org/api-flows-run | request/response shape, streaming, session_id |
| MCP server | https://docs.langflow.org/mcp-server | flows exposed as MCP tools, tool names/descriptions |
| Global variables | https://docs.langflow.org/configuration-global-variables | generic vs credential variables |
| Quickstart | https://docs.langflow.org/get-started-quickstart | Simple Agent template, the happy path |
| Docs index | https://github.com/langflow-ai/langflow/blob/main/docs/sidebars.js | the full list of component categories |

## Screen inventory

| ID | screen | how you get there | purpose | key components | states |
| --- | --- | --- | --- | --- | --- |
| S01 | Projects home | `/` (app launch) | list, open and manage flows | project sidebar, flow cards, card menu, New Flow button, import | empty (first run), filled, search with no results |
| S02 | New flow modal | S01 → New Flow | blank flow or template | template cards, Blank Flow | default |
| S03 | Flow editor | `/flow/:id` | build the graph | canvas, nodes, edges, minimap, zoom controls, top bar (name, Playground, Share, save state) | empty canvas, filled, building, node error, locked |
| S04 | Components sidebar | left pane inside S03 | find and add components | search, category accordion, draggable items | default, search with no results |
| S05 | Component inspector | click a node in S03 | edit every parameter, toggle tool mode | fields by type (text, multiline, number, slider, dropdown, toggle, secret), output preview | default, missing required field, has output |
| S06 | Playground | S03 → Playground | chat with the flow, watch agent steps | session list, message list, tool-call cards, input box, streaming | no Chat Input (blocked), empty, streaming, error, filled |
| S07 | API access modal | S03 → Share → API access | copy code to run the flow | tabs curl / Python / JS, endpoint name, tweaks | default |
| S08 | Import / export | S01 import button, S03 → Share → Export | move flows as JSON | file picker, download | invalid file |
| S09 | MCP server panel | S01 tab / S03 → Share → MCP Server | choose which flows are tools, copy client config | tool list with toggles, name/description edit, JSON snippet | no flows |
| S10 | Settings: Global variables | header → Settings | store values and credentials | table, Add New dialog (name, type, value) | empty, filled |
| S11 | Settings: Models | header → Settings | point at Ollama and see models | base URL, connection status, model list, pull model | connected, unreachable, no models |
| S12 | Settings: API keys | header → Settings | create/revoke keys for the run API | table, create dialog (key shown once) | empty, filled |
| S13 | Skills library (addition) | header → Skills | list, create, import skills | skill cards, search, import SKILL.md | empty, filled |
| S14 | Skill editor (addition) | S13 → a skill | write the skill | name, description, markdown body, preview | new, editing, validation error |
| S15 | Logs / traces | S03 → Logs | see each run's node timings and errors | run list, per-node rows | empty, filled |

## User flows

```
F01 Build and test an agent from a template           (the core loop)
    S01 → S02 Simple Agent → S03 pick Ollama model in Agent → S06 send a message → see tool call + answer
    happy path: 5 clicks + 1 message. Number to beat: 4.
    edge: Ollama unreachable, model doesn't support tools, empty message, model not pulled

F02 Build a flow from scratch
    S01 → S02 Blank → S04 drag Chat Input, Prompt, Ollama Model, Chat Output → connect ports → S05 set model → S06
    edge: incompatible port types (edge refused), cycle, missing required field, unconnected node

F03 Give an agent tools
    S03 add Calculator / URL / another Agent → S05 enable Tool Mode → connect Toolset → Agent.Tools → S06
    edge: two tools with the same name, tool throws, agent loops (max iterations)

F04 Give an agent skills (addition)
    S13 New skill → S14 write instructions → S03 add Skill component (choose skill) → connect → Agent.Skills → S06
    agent sees only names + descriptions; calls load_skill when one applies; body enters context
    edge: skill deleted while in a flow, huge skill body

F05 Call a flow from an app
    S03 → Share → S07 copy curl → (S12 create API key) → POST /api/v1/run/{id} → JSON reply
    edge: bad key (401), unknown flow (404), stream=true, tweaks override a field, session_id continues memory

F06 Use flows from an MCP client
    S09 enable flow as tool, edit name/description → copy JSON config → client lists + calls the tool

F07 Local RAG
    template "Document Q&A": Split Text → Ollama Embeddings → Vector Store (ingest) ; Chat Input → Vector Store (search) → Prompt → Ollama → Chat Output
    edge: embedding model missing, empty document

F08 Manage flows
    S01 card menu → rename / duplicate / export / delete ; S01 import JSON
```

## Components (UI)

| name | variants | states | used on |
| --- | --- | --- | --- |
| Button | primary, secondary, ghost, danger, icon | hover, focus, disabled, loading | all |
| Input / Textarea | text, secret (reveal), number, multiline | focus, error, disabled | S05, S10–S14 |
| Select / dropdown | static, with refresh (models) | open, loading, empty | S05, S11 |
| Toggle | | on, off, disabled | S05, S09 |
| Slider | | | S05 (temperature) |
| Modal | small, large | | S02, S07, S10, S12 |
| Tabs | | | S07, settings |
| Flow card | | hover, menu open | S01 |
| Canvas node | by category colour; tool mode | idle, selected, running, done, error | S03 |
| Port handle | by data type | connectable, invalid | S03 |
| Edge | | animated while running | S03 |
| Chat message | user, assistant, tool-call card, error | streaming | S06 |
| Toast | success, error | | all |
| Sidebar list | collapsible groups | | S03, S06 |
| Code block | copy button | copied | S07, S09 |
| Empty state | | | S01, S06, S10, S12, S13 |

## Inferred data model

```
Project   id, name, created_at                                    evidence: concepts-flows "Projects"   confidence: high
Flow      id, project_id, name, description, data (json: nodes, edges, viewport),
          endpoint_name (unique, nullable), locked, mcp_enabled, mcp_tool_name, mcp_description,
          created_at, updated_at                                   evidence: concepts-flows, concepts-publish, mcp-server  high
FlowVersion id, flow_id, data, created_at                          evidence: "Version History"  medium
Message   id, flow_id, session_id, sender (user|machine), sender_name, text,
          properties (json: tool calls, source component), created_at
                                                                   evidence: api-flows-run response, playground message logs  high
Variable  id, name (unique), type (generic|credential), value (encrypted if credential), created_at
                                                                   evidence: configuration-global-variables  high
ApiKey    id, name, key_hash, prefix, created_at, last_used_at     evidence: api keys docs  high
Run       id, flow_id, session_id, status, started_at, finished_at, trace (json per node)
                                                                   evidence: logs/traces docs  medium (guess on shape)
VectorChunk id, collection, text, metadata, embedding (json)       guess — Langflow uses external vector DBs; ours is local
Skill     id, name (slug, unique), description, body (markdown), created_at, updated_at
                                                                   addition — no evidence needed, our design
Setting   key, value (ollama_base_url, default_model)              evidence: bundles-ollama base URL  high
```

## What cannot be cloned (skip)

- Langflow's name, logo, docs text, templates' wording and screenshots.
- The 100+ third-party integration bundles (partner products, paid APIs). By request this clone is Ollama-only.
- Hosted cloud offering, enterprise SSO/governance, the community store and its users.
- Custom Python components with arbitrary code: deferred for security (sandboxing is its own project).

## Size

15 screens, 8 flows, 10 entities. Hard parts:

1. **Graph execution engine**: topological run of typed nodes, dynamic ports (prompt variables), tool mode turning any node into a callable tool.
2. **Agent loop on open models**: Ollama tool calling varies by model; need a robust loop with max iterations, streaming, and a skill-loading tool.
3. **Canvas editor UX**: typed edges, inspector, autosave, undo — done with React Flow.

Size: **L** for parity. A working thin slice (F01, F02, F03, F04, F05) is **M**.
