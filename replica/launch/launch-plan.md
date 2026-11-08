# Launch plan

## Before launch (2–3 weeks)

1. **Decide the licence** (see `pricing.md`) and add a LICENSE file.
2. **Run the to-run name checks** in `brand.md` (trademarks, domain, handles). Buy the domain only after they pass.
3. **Publish the package**: `kelvo` on PyPI and a multi-arch (amd64 + arm64) image on Docker Hub / GHCR. Lint descriptions with `listing.py`.
4. **Ship the S-sized fixes** from `fixes.md` first. They are the story: X1 offline-first guarantee + arm64 image, X2 Ollama capability badges, X3 real HTTP status codes, X4 import skills from a URL.
5. **Test on real Ollama** with qwen3, llama3.1, mistral-nemo and gemma3 (the build was only tested against a stand-in server). Record a 60-second screen capture of Simple Agent → Playground → tool call.
6. **Beta list**: point the landing form's `data-endpoint` at a form backend (Buttondown, Formspree, or a 20-line endpoint on your own server). Collect email + one optional question: "What would you build first?"
7. **Make the repo public** (or a public mirror) so "install it" has somewhere to point. Today it is private.

## Instrumentation, live before the first post

- Landing: privacy-friendly page analytics (Plausible or self-hosted Umami), events for *Join the beta* and *See how it works*.
- Product: **no telemetry by default.** It is a promise on the landing page. Offer an opt-in "send anonymous usage stats" toggle later, off by default.
- Errors: Sentry (or GlitchTip, self-hosted) on the landing page and the hosted demo only, not in user installs.

## Where the original's unhappy users talk

From the research: **the original's GitHub issue tracker**, which is the only source that could be read. Don't advertise there. Commenting "try my app" on another project's issues is spam and against GitHub's terms. Use it as research only.

Communities where local-model builders gather. These are well-known; **the research could not reach them, so they're unverified for this audience**. Read each one's self-promotion rules first:

- r/LocalLLaMA and r/ollama: post a build log or the "skills on small models" write-up, not an ad.
- Ollama's Discord (#showcase, if it exists): a short demo clip.
- Hacker News: Show HN (below).
- Lobste.rs (needs an invite), dev.to / Hashnode for the write-up.

## The posts

**Show HN** (title linted by `listing.py`):
> Show HN: Kelvo – a visual agent builder built on Ollama, with on-demand skills

First comment, in the brand voice: why it exists (local models treated as an afterthought, installs that take an afternoon); what's different (skills loaded only when needed, so 7–8B models stay sharp; three dependencies; no network calls at startup); what's not done (single-user, no team features, tested on a small set of models); and a direct question: "Which local models are you using for tool calling, and where do they break?"

**Write-up to go with it:** "Skills for small models: how loading instructions on demand keeps an 8B agent on task". Show the token count with all skills inlined vs loaded on demand, measured on real Ollama.

**Product Hunt** (after HN, once there's a public install): name, tagline and description from `listing.json`. Gallery: the three screenshots in `site/img/` plus the 60-second clip.

## The first 10 users, by hand

Not from scraping the original's issue authors. Find people who opt in:

1. Everyone who joins the beta list in week one: reply personally, ask what they'll build first.
2. People asking about tool calling or agents in r/ollama and r/LocalLLaMA threads: answer the question they asked; mention Kelvo only if it actually solves it.
3. Your own network: anyone running Ollama at work or at home.

For each of the 10: watch them install it (screen share), note every stuck moment, and ask the pricing question from `pricing.md`. Fix the top three stuck moments before the public launch.

## Launch-day checklist

- [ ] Landing live on the checked domain, form connected, analytics firing
- [ ] Public repo / package / image published; install command on the landing page tested from a clean machine
- [ ] Show HN posted on a weekday morning US Eastern, you available for 6 hours to answer
- [ ] Known limits listed in the README (single-user, no auth on the editor, tested models)
- [ ] Next: `/replica-deploy`
