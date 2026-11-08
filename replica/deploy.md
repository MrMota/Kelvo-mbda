# Deploy: Kelvo on your own machine

Kelvo is a personal tool: one account (yours), no domain, no public internet. So this checklist replaces the public-launch steps of the deploy skill (domain DNS, Stripe, OAuth, email, app stores, privacy/cookie pages) with what a private server needs: a locked-down container, private access, backups, and something that tells you when it's down.

**Status: not deployed yet.** Everything below was built and tested in the build sandbox. It goes live when you run the steps on your machine.

## 1. Preflight (run 2026-11-08)

| check | result |
| --- | --- |
| Backend tests (`make test`) | **33 passed**: engine, every template, agents/tools/skills, run API, MCP, sign-in (lockout, cross-site refusal, single account, setup token, password change), backup rotation, no network at startup, cold start < 3 s, model capabilities, Ollama API key |
| Browser click-through (`e2e/smoke.mjs`) | **13/13 passed**, against both the local server and the **built Docker image** |
| Production build (`npm run build`) | passes |
| Feature parity (`replica/tools/parity.py`) | **32/32 must-haves**, 88% weighted. X1 and X2 were missing at the start of this run and were built (see below) |
| Brand sweep (`replica/tools/sweep.py`) | **clean**: 0 findings |
| Contrast (`replica/tools/contrast.py`) | **0 failures**, light and dark |
| Dependency audit | npm: **0 vulnerabilities** (React Router upgraded 6.30 → 7.18.4 to clear 3 high + 2 moderate advisories); Python (`pip-audit`): **none found** |
| Docker image | builds; 256 MB; runs as non-root user `kelvo`; health check turns `healthy`; data and sign-in survive a restart |
| Compose | valid; **Ollama publishes no ports**; Kelvo binds to `127.0.0.1` unless you change `KELVO_BIND` |
| Secrets in git | none; `.env` and `*.db` are ignored |
| Backup + restore | tested: backup passes SQLite's integrity check; restoring it brings back flows and your account |
| Open bugs | none known |
| Not applicable (personal tool) | domain, DNS, email SPF/DKIM/DMARC, Stripe, OAuth, privacy policy/terms, cookie banner (only an essential sign-in cookie), store listings |

**Fixed during this run:** two must-have rows from the fix plan were not built, and the deploy was held until they were:
- **X1 offline-first**: tests now prove startup makes no network calls and a cold start takes < 3 s (measured 0.36 s). Multi-arch is covered by building on your own machine from multi-arch base images.
- **X2 Ollama capabilities**: the model picker tags each model (tools, vision, embed) from Ollama's `/api/show`; an Agent whose model can't call tools shows a warning before you run it; optional Ollama API key (write-only) for ollama.com or a protected Ollama.

**Also fixed:** Compose published Ollama's port 11434 to every network (Ollama has no login) and Kelvo's port to every network. Both are now private by default.

**Sandbox-only notes:** the Docker build here needed this sandbox's proxy settings and a mirror for one base image (Docker Hub rate-limited the shared IP). Those changes live only in a scratch copy of the Dockerfile; the repo's `Dockerfile` is unchanged and needs nothing special on your machine. **Not tested here:** a real Ollama with real models (a stand-in was used), a GPU, and Tailscale.

## 2. Install on your machine (Docker, recommended)

You need Docker with Compose, and a machine with enough RAM for your models (8 GB+ for 7–8B models; a GPU or Apple silicon makes agents much quicker).

```bash
git clone https://github.com/MrMota/MBDAflow.git kelvo && cd kelvo
cp .env.example .env          # set KELVO_USERNAME and KELVO_PASSWORD (first start only)
docker compose up -d --build
docker compose exec ollama ollama pull qwen3:8b          # a model that can call tools
docker compose exec ollama ollama pull nomic-embed-text  # for Document Q&A
```

Open **http://127.0.0.1:7860**, sign in, then **Settings → Models**: pick `qwen3:8b` as the default model. After the first sign-in, delete the two account lines from `.env`. They're only read once.

No `.env` account? `docker compose logs kelvo` shows a one-time setup token; the app asks for it.

**NVIDIA GPU:** uncomment the `deploy:` block under `ollama` in `docker-compose.yml` (needs the NVIDIA Container Toolkit). **Mac:** Docker can't use the Apple GPU, so run Ollama natively (`brew install ollama`, then `ollama serve`). In `docker-compose.yml`, remove the `ollama` service and its `depends_on`, and set `OLLAMA_BASE_URL: http://host.docker.internal:11434`. Or skip Docker and use the install below.

### Without Docker (systemd, Linux)

```bash
git clone https://github.com/MrMota/MBDAflow.git ~/kelvo && cd ~/kelvo
make install && make build
.venv/bin/kelvo set-password          # create your account
```

Then edit and install `deploy/kelvo.service` (and `deploy/kelvo-backup.{service,timer}` for nightly backups). The comments in each file have the exact commands. Ollama: install it from ollama.com; it runs as its own service on `127.0.0.1:11434`.

## 3. Reaching it from your other devices (no domain)

Pick one. Never `0.0.0.0` on a machine with a public IP.

| option | how | address |
| --- | --- | --- |
| **This machine only** (default) | nothing to do | `http://127.0.0.1:7860` |
| **Tailscale** (recommended for phone/laptop anywhere) | install Tailscale on the machine and your devices; set `KELVO_BIND=` your machine's Tailscale IP (`tailscale ip -4`) in `.env`; `docker compose up -d` | `http://100.x.y.z:7860` from your devices only |
| **Tailscale + HTTPS** | keep `KELVO_BIND=127.0.0.1`; run `tailscale serve --bg 7860`; in `.env` set `KELVO_SECURE_COOKIE=1` and `KELVO_ALLOWED_ORIGINS=https://<machine>.<tailnet>.ts.net` | `https://<machine>.<tailnet>.ts.net` |
| **Home network** | `KELVO_BIND=0.0.0.0` (or the machine's LAN IP); only on a home network you trust | `http://<lan-ip>:7860` |

If saving anything fails with "Cross-site request refused" behind a proxy, add the exact address you browse to (scheme + host) to `KELVO_ALLOWED_ORIGINS`.

## 4. Backups

Everything (flows, skills, chats, settings, account, API keys) is in one SQLite file. `kelvo backup` copies it safely while Kelvo runs and checks the copy.

```bash
# Docker: nightly at 03:17, keeps the newest 14, inside the kelvo volume
crontab -e
17 3 * * * cd ~/kelvo && docker compose exec -T kelvo kelvo backup --keep 14 >> ~/kelvo/backup.log 2>&1
# Off the machine too (weekly is plenty): copy them out, then to another disk / cloud drive
docker compose cp kelvo:/data/backups ./backups
```

**Restore** (tested): stop Kelvo, put the backup in place of the database, start.

```bash
docker compose stop kelvo
docker compose cp ./backups/kelvo-YYYYMMDD-HHMMSS.db kelvo:/data/kelvo.db
docker compose run --rm --entrypoint sh kelvo -c 'rm -f /data/kelvo.db-wal /data/kelvo.db-shm'
docker compose start kelvo
```

Ollama's models aren't backed up; they can always be pulled again.

## 5. Updating

```bash
cd ~/kelvo && docker compose exec -T kelvo kelvo backup   # always back up first
git pull && docker compose up -d --build
docker compose exec ollama ollama pull qwen3:8b            # optional: newer model weights
```

New tables are added automatically on start. There is no migration system for changed columns yet (fix-plan item X6); until there is, read the commit messages before pulling, and keep that backup.

## 6. Watching it

For one person, this is enough:

- **Auto-restart:** both services are `restart: unless-stopped`; the Kelvo container has a health check (`docker compose ps` shows `healthy`).
- **Logs:** `docker compose logs -f kelvo` (sign-in failures, run errors). **Run logs** inside Kelvo (Logs button in the editor) show every run, per component, with timings and errors.
- **Optional alert** if the machine or Kelvo goes down: a free healthchecks.io check pinged from cron, e.g. `*/5 * * * * curl -fsS http://127.0.0.1:7860/api/health && curl -fsS https://hc-ping.com/<your-uuid>` (you create the account and the UUID).
- No analytics, no error-tracking service: Kelvo sends nothing anywhere.

## 7. First week

- [ ] Do the core flow on the real thing: Simple Agent → Playground → "what is 12% of 340?", and check the calculator tool call appears. Then the same from your phone.
- [ ] Try a few models; note which ones call tools reliably on your hardware (the picker's "tools" tag tells you which *can*).
- [ ] Confirm the first nightly backup exists (`docker compose exec kelvo ls /data/backups`) and copy one off the machine.
- [ ] Sign in from a second device, change your password in Settings → Account, and check the first device was signed out.
- [ ] Remove `KELVO_USERNAME` / `KELVO_PASSWORD` from `.env`.

Live URL: *none yet. Fill in the address you chose in step 3.*
