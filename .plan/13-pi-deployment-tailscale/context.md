# #13: Context

## Issue Description

Deploy the full application stack (backend + frontend containers) to the Raspberry Pi so it runs persistently there — `--restart unless-stopped`, survives reboots — replacing the current workflow of running `backend/.venv/bin/uvicorn app.main:app --reload` locally on the dev Mac. Tailscale then makes the running app reachable from any Apple device off the home LAN, same pattern `#13.1` already proved out for the NAS Postgres route, just applied to the app itself.

Originally blocked by `#8`, `#10.1`–`#10.5` (all done/merged) and, as of this session, `#13.1` (Tailscale subnet routing, done) and `#13.2` (dropped the unused email notification channel, done). Nothing blocking a start now.

## Component / Route Summary

### Current State

- `docker-compose.yml` already defines `backend` and `frontend` services — `platform: linux/arm64`, `restart: unless-stopped`, `env_file: .env`, on the `app` network, with `backend` mounting `/opt/tradingagents:/opt/tradingagents`. Also has `pihole` (shipped via `#34`, already running on the Pi, isolated on its own `pihole` network).
- The repo is **already cloned on the Pi** at `~/projects/youn-server`, via a read-only GitHub deploy key set up during `#34`'s work (this repo is private — confirmed via `gh repo view`). Only `backend`/`frontend` were left un-deployed at that time since their `.env` secrets weren't set up yet.
- Pi is fully provisioned otherwise: OS, SSH (LAN + Tailscale), Docker Engine (`youn` user in `docker` group), Node.js, Claude Code CLI. See `[[project-pi-setup-status]]`.
- `backend/app/main.py`'s `lifespan` starts an APScheduler job (`poll_prices`, every 6h, fires immediately on startup) and an `asyncio.Queue`-based event dispatcher — no auto-migration call (`alembic upgrade head` is not invoked anywhere in the startup path).
- `backend/Dockerfile` runs as a non-root user (`chown -R 1000:1000`, `USER 1000`), base image `mcr.microsoft.com/playwright/python:v1.44.0-jammy` (needed for Playwright-based scraping).
- `frontend/src/app/api/proxy/[...path]/route.ts` proxies browser requests server-side to `BACKEND_URL` (Docker-internal `http://backend:8000`) — the browser never needs direct access to port `8000` for normal app use, only this issue's explicit `GET /api/health` acceptance criterion does.
- `DATABASE_URL` in the Pi's eventual `.env` points at the NAS (`<nas-ip>:5433`) — same DB local dev has been using, reachable now both on-LAN and off-LAN via `#13.1`'s subnet route.
- No `.env` exists yet on the Pi for `backend`/`frontend` — only whatever `#34` needed for `pihole` (at minimum `PIHOLE_WEBPASSWORD`, possibly nothing else).
- Notification channel is Pushover-only as of `#13.2` — `PUSHOVER_API_TOKEN`/`PUSHOVER_USER_KEY` are the real env var names (a pre-existing `.env.example` typo, `PUSHOVER_APP_TOKEN`, was corrected during `#13.2`).

### Target State

- Pi's `.env` populated with real secrets (`PUSHOVER_API_TOKEN`, `PUSHOVER_USER_KEY`, `API_KEY`, `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY`, `TRADINGAGENTS_LLM_PROVIDER=anthropic`, `TRADINGAGENTS_OUTPUT_LANGUAGE=English`, `DATABASE_URL`), `chmod 600`.
- TradingAgents freshly cloned directly on the Pi at `/opt/tradingagents` (decided against copying the Mac's existing clone — no benefit, the `.venv` has to be rebuilt fresh either way since Mac's is Darwin-only).
- `docker compose up -d` running `backend`+`frontend`+`pihole` together on the Pi.
- TradingAgents' `.venv` built **inside** the running `backend` container (not on the Pi host), smoke-tested with `python -c "import tradingagents"`.
- Local Mac `uvicorn` retired for real use once the Pi is verified live — the Pi becomes the single instance polling/dispatching against the shared NAS DB, avoiding the double-scheduler risk described in `challenges.md`.
- End-to-end Pushover push confirmed on a real device, from a real triggered alert.

## Impact & Risk

### Files Changed
None in this repo — purely operational (Pi SSH commands, `.env` population, container startup). If `.env.example` needs a follow-up correction discovered during the deploy, that's a small separate doc edit, not core to this issue.

### Dependencies
- **`#13.1`** — provides the Postgres reachability this deploy relies on (already done, verified).
- **`#13.2`** — provides the finalized single-channel (Pushover) notification config this deploy's `.env` populates (already done).
- **`#34`** — already deployed `pihole` from this same `docker-compose.yml`; this issue adds `backend`/`frontend` alongside it without disturbing `pihole`'s already-working state.

### Breaking Changes
None to the app itself. The one real operational risk is running the Pi's `backend` and the Mac's local `uvicorn` simultaneously against the same NAS DB post-deploy — see `challenges.md`.
