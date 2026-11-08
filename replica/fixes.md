# What users of the original want fixed, and what Kelvo does about it

## Sample, and how far to trust it

- **225 rows, one platform: Langflow's public GitHub issue tracker** (bug reports plus its feature-request board), 2023-02-24 → 2026-10-09. Collected with the official GitHub search API by `collect_github.py`: the 30 most-reacted issues for each of 14 queries, deduplicated.
- **Not reached:** Hacker News (Algolia API), Reddit, G2, Trustpilot, Capterra and Product Hunt. All failed from this sandbox: connection refused or DNS failure. There are no star-rated reviews in the sample.
- **What that biases:** GitHub issues come from developers who self-host, and they skew toward bugs and power-user requests. "Votes" means GitHub reactions on the issue. A count is a count of *issues*, not people. Every theme here is from **one platform**, so by the skill's rule none is a confirmed cross-source trend. Read the lists as strong leads, not proof.
- **To widen it:** allow `hn.algolia.com` and Reddit in the environment's network settings, or paste review rows into `reviews.csv` by hand (source, url, date, rating, text), then rerun `python3 replica/reviews.py replica/reviews.csv --out replica/feedback.md`.

Full ranking with every link: `feedback.md`. Raw rows: `reviews.csv`.

---

## 1. What they hate

Complaints about things the original does.

| # | problem | issues | votes | quotes |
| --- | --- | --- | --- | --- |
| H1 | **Installing and starting it is slow, heavy and fragile.** Long pip installs, missing modules after install, desktop app that won't start, 20–45 min startups on servers without internet | 9 | 27 | "Currently it takes more than 5 hours to realize that the installation failed. Extremely bad user experience." ([#4964](https://github.com/langflow-ai/langflow/issues/4964)) · "takes almost 45 minutes to startup. On my laptop it gets started in 1 minute only." ([#9039](https://github.com/langflow-ai/langflow/issues/9039)) |
| H2 | **Ollama is a second-class citizen.** Models listed but not loaded, streaming lost behind the Agent, embedding models missing from the picker, Ollama Cloud unusably slow | 6 | 16 | "When connecting the Ollama component directly to Chat Input/Output, streaming works correctly. However, when the Ollama component is connected via an Agent component, responses are buffered and only displayed after full completion." ([#10968](https://github.com/langflow-ai/langflow/issues/10968)) · "Agent and LLM components show Ollama models but do not load them, keeps querying Ollama with POST /api/show" ([#12147](https://github.com/langflow-ai/langflow/issues/12147)) |
| H3 | **Upgrades break working flows** (thin: 4 issues, 1 source) | 4 | 8 | "After upgrading to langflow 1.2.0, none of my flows work anymore." ([#6870](https://github.com/langflow-ai/langflow/issues/6870)) |
| H4 | **API hides the real error behind a 500** (thin: 1 issue) | 1 | 7 | "errors originating from LLM components (for example, 429 Too Many Requests rate-limit errors from an LLM provider) are not propagated to the API response. Instead, the Langflow API consistently returns a 500" ([#11534](https://github.com/langflow-ai/langflow/issues/11534)) |

## 2. What is missing

Features asked for by name. ✅ = Langflow has since shipped it (per its current docs), so for us it is parity, not an edge.

| # | request | issues | votes | quote | original now | Kelvo now |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | Team collaboration: roles, flow sharing, org access control | 4 | 83 | "allow multiple users to view, edit, and collaborate on flows within the same self-hosted Langflow deployment" ([#8531](https://github.com/langflow-ai/langflow/issues/8531)) | partial | no (single user) |
| M2 | SSO (OIDC/OAuth2), disable public sign-up | 2 | 70 | "cannot get security approval for a self hosted solution without Single Sign On (SSO)" ([#2855](https://github.com/langflow-ai/langflow/issues/2855)) | ✅ (external auth docs) | no |
| M3 | Self-hosted / OpenAI-compatible model servers (vLLM, llama.cpp, LocalAI, TGI) | 7 | 46 | "many LLM Inference Server provide the OpenAI Chat Interface" ([#7300](https://github.com/langflow-ai/langflow/issues/7300)) | ✅ bundles | Ollama only |
| M4 | Export a flow as standalone, readable Python | 3 | 37 | "export the corresponding Python code that can run the flow as a standalone script—without requiring the langflow GUI" ([#8272](https://github.com/langflow-ai/langflow/issues/8272)) | partial (`lfx run`) | no |
| M5 | **Skills** integration | 1 | 21 | "Hope Langflow can extend to support for external Skills integration" ([#11547](https://github.com/langflow-ai/langflow/issues/11547)) | not in docs | **yes** (library, SKILL.md, load on demand) |
| M6 | Human-in-the-loop approval | 1 | 19 | "allow human operators to intervene at critical decision points, review outputs before they're passed to subsequent agents" ([#6867](https://github.com/langflow-ai/langflow/issues/6867)) | ✅ | no |
| M7 | Workflow version history | 1 | 14 | "enable users to view, name, and restore previous versions of a workflow" ([#8634](https://github.com/langflow-ai/langflow/issues/8634)) | ✅ | no |
| M8 | ARM64 Docker images (Raspberry Pi) | 1 | 13 | "I want to host langflow using docker image on ARM64 device (raspberry pi)" ([#1976](https://github.com/langflow-ai/langflow/issues/1976)) | unknown | image builds on arm64; not published |
| M9 | Guardrails (thin) | 1 | 8 | ([#4863](https://github.com/langflow-ai/langflow/issues/4863)) | ✅ component | no |
| M10 | Scheduled / cron runs (thin) | 1 | 6 | ([#5541](https://github.com/langflow-ai/langflow/issues/5541)) | unknown | no |

## 3. What is unsolved

Whole groups the original serves badly. These become positioning.

| # | group | evidence |
| --- | --- | --- |
| U1 | **People running their own models, especially offline or air-gapped.** They get the slowest install, the buggiest model integration, and startups that hang without internet. | H1 + H2 + M3: 22 issues, 89 votes. Startups of "around 20 minutes" with no internet vs "1-2 minutes" with it ([#9068](https://github.com/langflow-ai/langflow/issues/9068)) |
| U2 | **Teams self-hosting inside companies with security review.** They need SSO, roles, shared flows. | M1 + M2: 6 issues, 153 votes, the most-voted requests in the sample |
| U3 | **Developers who want to leave the canvas**: prototype visually, then own plain code with no lock-in | M4: 3 issues, 37 votes, asked for since 2023 |

---

## 4. Fix plan

Ranked by evidence × cheapness. All of these are new rows in `features.csv` with `original = no`.

| # | build / change | size | skill | evidence |
| --- | --- | --- | --- | --- |
| X1 | **Offline-first guarantee**: no outbound calls at startup (test it in CI with the network off), startup-time budget < 3 s, publish multi-arch (amd64 + arm64) Docker images | S | replica-backend / replica-deploy | H1 (9 issues, 27 votes), M8 (13 votes) |
| X2 | **Ollama-first polish**: show each model's capabilities (tools, vision, embedding) in the picker from one cached `/api/show` per model; warn when an agent uses a model without tool support; Ollama API-key field so ollama.com Cloud works | S–M | replica-build | H2 (6 issues, 16 votes) |
| X3 | **Honest API errors**: map model-server failures to real status codes (404 model not pulled, 429, 502 unreachable, 504 timeout) with `node_id` and the provider's message | S | replica-backend | H4 (7 votes) |
| X4 | **Skills from anywhere**: import a skill from a URL, a GitHub folder or a `.zip` of SKILL.md bundles; export all skills as one bundle | S | replica-build | M5 (21 votes): our differentiator, make it complete |
| X5 | **Leave the canvas**: `kelvo exec flow.json "input"` headless runner + "Export → Python script" that runs a flow with only the `kelvo` package | M | replica-build | M4 (3 issues, 37 votes) |
| X6 | **Safe upgrades**: schema version table + ordered migrations; a `format_version` in flow JSON and an import upgrader; test every template still runs after migrating | M | replica-backend | H3 (4 issues, 8 votes, thin) |
| X7 | **Version history** (snapshot on save, name, restore) | M | replica-build | M7 (14 votes), parity |
| X8 | **Human approval for tool calls** (per-tool "requires approval", Approve/Reject in the Playground) | M | replica-build | M6 (19 votes), parity |

Not in the plan (yet), and why:
- **Team mode (SSO, roles, sharing)**: the strongest demand (153 votes) but an L build, and it changes the product from a local tool to a server product. Pick it only if you choose angle B below.
- **OpenAI-compatible servers (M3)**: well supported (46 votes), but your brief was Ollama-only. It is a one-component M job if you want "open models anywhere" instead of "Ollama". **Your call.**
- Pricing and billing: no complaints in this sample (GitHub issues rarely carry them). Nothing to hand to `/replica-launch` yet.

## 5. The angle

**A. Local-first (recommended)**
> For developers who run their own models and are tired of local models being an afterthought (heavy installs, flaky Ollama support, startups that hang without internet), Kelvo is built on Ollama from the ground up: a three-package install, works fully offline, and every component speaks Ollama natively.
> Evidence: U1, 22 issues, 89 votes (one platform: GitHub). Already true of the build (3 Python dependencies, no startup network calls, Ollama streaming through agents); X1–X3 make it provable.

**B. Self-hosted for teams**
> For companies that must self-host AI agents but can't pass security review without SSO and access control, Kelvo gives every team private, shareable flows behind your own login.
> Evidence: U2, 6 issues, 153 votes (one platform). Biggest demand, but the largest build and a different product.

**C. Agents with skills**
> For builders whose agents get worse as you cram more instructions in, Kelvo agents carry a library of skills and load only the one they need, so small local models stay sharp.
> Evidence: M5, 1 issue, 21 votes. Thin as a market signal, so use it as the *feature that proves* angle A rather than as the angle itself.

**Recommendation: A, with C as its headline feature.** It matches your brief (Ollama, agents, skills). It is backed by the widest spread of complaints in the sample, and the current build already delivers most of it. B is the larger market if you later want to sell to companies; it would sit on top of A, not replace it.

Use none of the original's name in your product name, ads or store listing. A factual comparison page is a question for a lawyer in your country.
