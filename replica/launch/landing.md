# Landing page

Built at `site/index.html` (static, no build step; images in `site/img/`, real screenshots of the product). Contrast check: `python3 replica/tools/contrast.py site/index.html` → 0 failures. No horizontal scroll at 390 px. Light and dark.

| section | content | source |
| --- | --- | --- |
| Hero | **AI agents that run on your own models.** Visual builder for agents, tools and skills; every model call goes to your own Ollama; three Python packages, starts in under a second, keeps working offline. Button: *Join the beta*. Screenshot: the Skilled Agent canvas | angle A (`fixes.md`); "under a second" measured: 0.36 s cold start with a fresh database, 3 runs, 2026-11-08 |
| The problem | "Getting started eats your afternoon" and "Your models feel bolted on". Paraphrased, no reviewer quotes | H1 (9 issues, 27 votes), H2 (6 issues, 16 votes) |
| How it works | Point it at Ollama → build on the canvas → talk to it, then ship it | core flow F01 / F05 |
| Features | Skills first (with screenshot), then Ollama-native, Light, Clear errors (fixes), then agents, local RAG, REST + MCP (parity) | M5, H2, H1, H4; parity rows |
| Pricing | Community $0 · Team $49/server/month (*in development, not on sale*) · Support | `pricing.md` |
| FAQ | GPU? Which models for agents? Does anything leave my machine? Import from other builders? (honest: not yet) Apps and agents using flows? Ready for teams? (honest: not yet) | objections from research + product limits |
| Final CTA | Email field, *Join the beta*. Posts JSON `{email}` to the form's `data-endpoint` | wire it up at deploy |

What's deliberately **not** on the page: testimonials, user counts, star ratings, logos, "trusted by". There are no users yet. The original's name appears nowhere. Ollama is named as a compatible tool, with a trademark note in the footer.

Every product claim was checked against the build:

| claim | true because |
| --- | --- |
| three Python packages | `backend/pyproject.toml` dependencies: fastapi, uvicorn, httpx |
| starts in under a second | measured 0.36 s (cold, fresh DB) on the build machine |
| no network calls at startup / no telemetry | startup only creates the SQLite schema; no analytics code exists |
| streaming through an agent | Agent streams tokens when wired to Chat Output (tested) |
| tells you when a model can't call tools | `ollama.py` rewrites Ollama's "does not support tools" error |
| skills load on demand, SKILL.md import/export | `components/agent.py`, `/api/skills/import`, `/export` (tested) |
| REST API with keys, sessions, streaming; MCP server | tested in `backend/tests` |

**Before publishing:** connect the beta form (`data-endpoint`), and replace "Kelvo is an independent project" if your legal entity name differs.
