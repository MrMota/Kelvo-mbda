# Brand: Kelvo

Angle (from `fixes.md`): **local-first agents, with skills as the headline feature**. For people who run their own models and are tired of local models being an afterthought.

## 1. Name

### 20 candidates

| style | names |
| --- | --- |
| descriptive / compound | Hearthkit, Skillwright, Skillcraft, Lanternwork, Quillwork, Emberwork, Homeloom |
| metaphor | Hearth, Croft, Larder, Burrow, Cairn, Bothy, Wayhouse, Rookery, Moraine, Holloway |
| invented | **Kelvo**, Talvi, Ostra, Wickett, Nookery |

### Cut to 5 (plus the working name)

Filters: not confusable with the original (no "-flow", no "lang"), not with another app in this category, spellable on first hearing, no awkward meaning.

| name | why it survived / failed |
| --- | --- |
| **Kelvo** ✅ chosen | Invented, 5 letters, says it once and people can spell it. No meaning in English, Spanish, Portuguese, French or German that I know of. **Verify with native speakers** of your target markets. |
| Hearthkit | On-angle (home + toolkit). Runner-up. |
| Lanternwork | On-angle metaphor, but 11 letters. |
| Talvi | Finnish for "winter". An 80★ Clojure web stack and an AI voice assistant ("Talvio") use near names. |
| Wayhouse | Neutral metaphor; weak link to the angle. |
| ~~MBDAflow~~ | Working name. **MBDA** is a large European defence/missile company (a registered mark, and an unwanted association); "-flow" sits beside Langflow, Flowise and Prompt flow in this exact category. Dropped. |
| ~~Bothy~~ | A GitHub repo named "bothy" is already an Android agent runtime with an MCP server (same category). |
| ~~Nookery~~ | Name of a popular (1.5k★) unofficial Animal Crossing port. |

### Checks for Kelvo

Run 2026-11-08 from the build sandbox. Trademark, domain and social lookups are **blocked from the sandbox** and are marked *to run*. Nothing is "available" until someone runs it. These are screening checks, not legal clearance: have a trademark lawyer search before you spend money on the name.

| check | where | result |
| --- | --- | --- |
| PyPI package `kelvo` | pypi.org/pypi/kelvo/json | **free** (404), 2026-11-08 |
| npm package `kelvo` | registry.npmjs.org/kelvo | **free** (404), 2026-11-08 |
| GitHub repos named kelvo | GitHub search API | 118 repos match "kelvo" in name; top hits are a 2★ Linux smart-lights tool ("without a cloud") and unrelated personal repos. **No AI/agent project found.** 2026-11-08 |
| GitHub user/org `kelvo` | github.com/kelvo | *to run* (API blocked for this session) |
| US trademark, classes 9 + 42 | tmsearch.uspto.gov | *to run* |
| EU trademark | euipo.europa.eu eSearch / TMview | *to run* |
| Canada | ised-isde.canada.ca | *to run* |
| Global | WIPO Global Brand Database | *to run* |
| Domains | kelvo.com, kelvo.dev, kelvo.ai, getkelvo.com | *to run* (`whois kelvo.dev`) |
| App Store / Play | search "Kelvo" | *to run* (not critical: web + self-hosted product) |
| Handles | X, GitHub, Discord, YouTube | *to run* |
| Web | search "Kelvo AI", "Kelvo agents" | *to run* |

## 2. Palette

The original's marks use purple `#7528FC`, pink `#F480FF` and hot pink `#FF3276` (read from its public logo SVGs). Kelvo's primary is **deep teal**, a different hue family (≈173° vs 263°/295°/345°). The sweep flags any colour within RGB distance 40 of the original's three.

| role | light | dark |
| --- | --- | --- |
| accent (buttons, focus, brand mark) | `#0b7c70` | `#2bb8a6` |
| accent-strong (links, active nav) | `#086358` | `#4fd2c0` |
| accent-soft (selected backgrounds) | `#e1f3f0` | `#11302c` |
| text / text-2 / text-3 | `#121821` / `#4a5565` / `#636d7c` | `#e8ecf1` / `#aab3bf` / `#8590a0` |
| danger / warn / ok | `#c0302f` / `#a8730a` / `#1d9a5b` | `#f06363` / `#d9a22a` / `#1d9a5b` |
| input borders | `#8a94a3` | `#667386` |

Port colours (data types on the canvas): Message `#2f6fe4`, Text `#0b7f9c`, Data `#c45a0c`, Language Model `#5b6678` (was a pink close to the original's), Embeddings `#0b8478`, Tool `#1b8545`, Skill `#9a7206`, with brighter twins in dark mode.

`python3 replica/tools/contrast.py frontend/src/styles.css` → **0 failures** in light and dark (text 4.5:1, UI graphics and ports 3:1). Before this pass there were 12 failures, including white on the old teal button (3.3:1).

## 3. Logo brief

- **Idea:** a small, steady light you own. A rounded "K" whose upper arm becomes a node with a short connector, as if one step of a flow sits inside the letter. Local, self-contained, a little warm.
- **Mark type:** symbol + wordmark; the symbol alone is the app icon and favicon.
- **Wordmark:** lowercase "kelvo", geometric sans, medium weight, slightly open tracking.
- **Colour:** teal `#0b7c70` on white, or white on teal. One colour only; no gradients.
- **Must work** at 16 px (favicon: symbol only, no connector detail below 24 px) and at 1024 px.
- **Deliverables:** SVG (symbol, wordmark, lockup; light and dark); app icon 1024×1024 PNG with no transparency; favicon set (16, 32, 48 ICO + 180 apple-touch + SVG); social image 1200×630; GitHub social preview 1280×640.
- **Must not resemble the original's mark:** no stacked/chained bar shapes, no purple–pink pairing, no gradient. Put the original's logo next to every draft and check shape, colour pair and letterform.
- **Current placeholder** (in `index.html` and the top bar): two dots and a connector on a teal square. It is generic and fine for now; replace it with the designed mark.

## 4. Voice

**Plain** — not dumbed down. **Grounded** — talks about your machine, your models, what actually happens; not dry. **Warm** — friendly and calm; not cute.

| do | don't |
| --- | --- |
| "Every model call goes to your own Ollama." | "Powered by cutting-edge AI." |
| "Can't reach Ollama at 127.0.0.1:11434. Start it with `ollama serve`." | "Something went wrong. Please try again later." |
| Short verbs on buttons: "New flow", "Send", "Run" | "Get started now!", "Unleash your agents" |
| One idea per sentence, numbers when we have them | Stacked clauses, hype words (magic, supercharge, revolutionary) |
| Say what happens next: "This can't be undone." | Make the user guess, or blame them |

### Rewritten strings (the 10 most-seen)

| where | before | after |
| --- | --- | --- |
| Home, empty | Build your first agent / Start from a template like Simple Agent, or a blank canvas. Everything runs on your Ollama models. | **Your first agent is two clicks away** / Pick Simple Agent for one that already works, or start blank. Every model call goes to your own Ollama. |
| New flow dialog | Start a new flow | **New flow** |
| Canvas, empty | Empty canvas / Drag components from the left… | **Nothing here yet** / Drag a component in from the left, or click one. A good start: Chat Input → Agent → Chat Output. |
| Playground, empty | Chat with your flow / Messages go through the flow… | **Say something to your flow** / Replies come from your own Ollama models. When the agent uses a tool, you'll see the call and its result here. |
| Playground, no input | No Chat Input / …execute the flow once. | **This flow doesn't take chat** / Add a Chat Input to talk to it here, or press Run to run it once. |
| Status, offline | Ollama offline | **Ollama not running** |
| Error, unreachable | Cannot reach Ollama at … Is `ollama serve` running? | **Can't reach Ollama at …. Start it with `ollama serve`, or fix the URL in Settings → Models.** |
| Error, model missing | …pull it first (Settings → Models…) | **…this model isn't on your Ollama yet. Pull it in Settings → Models, or run `ollama pull <model>`.** |
| Error, no tools | …pick a tool-capable model such as… | **…this model can't call tools. Pick one that can, such as qwen3, llama3.1 or mistral-nemo.** |
| API key created | Copy it now. It won't be shown again. | **Copy it now. This is the only time you'll see it.** |
| Delete flow | Delete "X"? Its chat history goes too. | **Delete "X" and its chat history? This can't be undone.** |
| Run done | Flow ran successfully | **Run finished** |

## 5. Sweep

`python3 replica/tools/sweep.py . --config replica/brand.json` searches file contents and names for the original's name, company and domains, the old working name, and colours near the original's. Result recorded in the commit that adds this file.

Still to check by eye once the logo exists: favicon, page title, OG/social image, Docker Hub and PyPI descriptions.

Note: the GitHub repository is still called `MBDAflow`. Renaming it (Settings → General on GitHub) is up to you; GitHub redirects the old URL.
