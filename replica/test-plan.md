# Test plan and results

Run on 2026-11-08 against the fake Ollama (`mbdaflow.fake_ollama`). No real model was available in the build sandbox, so model *quality* is untested; protocol, wiring and UI are.

## Automated

| suite | covers | result |
| --- | --- | --- |
| `backend/tests` (pytest, 19 tests) | engine, every template end to end, agent tool loop, memory, skills (inline + library + load_skill), multi-agent, RAG ingest idempotency, structured output, If-Else branching, cycle rejection, missing-model error, run API (auth, tweaks, alias, stream), MCP (initialize, tools/list, tools/call), skills CRUD + SKILL.md round trip, credential masking + `${VAR}` substitution, flow CRUD + lock | 19/19 pass |
| `e2e/smoke.mjs` (Playwright) | F08 home, F01 template → playground → tool call, memory, F02 drag-drop + connect + invalid edge refused + autosave + chat, inspector, F04 create skill + agent loads it, F05 API key + share snippets + MCP toggle, dark mode, 390px width | 10/10 pass |
| template layout check | no overlapping nodes in Simple / Skilled / Multi-Agent / Document Q&A | pass |

## Edge cases covered

- Ollama unreachable → "Cannot reach Ollama at … Is `ollama serve` running?" (node + playground)
- Model not pulled → error suggests pulling it; run logged as `error`
- Model without tool support → error names tool-capable models
- Incompatible ports → connection refused on the canvas
- Removing a `{variable}` from a prompt drops its edges
- Cycle → run refused with a clear message
- Inactive If-Else branch → downstream nodes skipped, not errored
- Agent loops → capped by *Max tool rounds*; tool exceptions are returned to the model
- URL tool → private / loopback addresses blocked (SSRF)
- Locked flow → canvas read-only, PATCH of data returns 423

## Bugs found and fixed during the click-through

| # | severity | bug | fix |
| --- | --- | --- | --- |
| 1 | medium | Template nodes overlapped (Calculator over Current Date, Chat Input over URL) | re-laid out all templates; added an automated overlap check |
| 2 | low | Agent node very tall: library-skills checklist rendered on the canvas | node shows a one-line summary; editing moved to the settings panel |
| 3 | low | Minimap covered the canvas when the Playground was open | minimap hidden while the Playground is open |

## Not yet tested

- Real Ollama models (tool-call formats vary by model family): run `make run` against a real server with `qwen3` / `llama3.1`.
- Pulling a model from Settings (needs network access to the Ollama registry).
- Long-running generations and cancelling mid-stream.
