# #13: Implementation

## Steps

### 1. Pi — get the latest repo
- [x] `ssh youn@<pi-tailscale-ip>` (or LAN: `youn@<pi-lan-ip>`)
- [x] `cd ~/projects/youn-server && git pull` — picks up `#13.1`/`#13.2`'s changes (already-cloned repo from `#34`'s deploy key setup)
- [x] Confirm the deploy key still has at least read access: `git pull` succeeding is sufficient proof, no separate check needed

### 2. Pi — reconcile and populate `.env`
- [x] Check what's already there: `cat ~/projects/youn-server/.env` (likely just `PIHOLE_WEBPASSWORD` from `#34`, possibly nothing else)
- [x] Compare against the Mac's local `.env` `PIHOLE_WEBPASSWORD` value — if they differ, decide which is authoritative before overwriting (mismatched value on restart could reset Pi-hole's admin password)
- [x] Transfer the Mac's `.env` to the Pi (`scp` over Tailscale/LAN), preserving whichever `PIHOLE_WEBPASSWORD` is correct
- [x] `chmod 600 ~/projects/youn-server/.env`
- [x] Confirm `DATABASE_URL` still points at `<nas-ip>:5433` (NAS) — should already be correct per the earlier off-LAN/on-LAN revert this session

### 3. Pi — verify Docker starts on boot (don't build a redundant systemd unit)
- [x] `systemctl is-enabled docker` — the `get.docker.com` install script typically enables this by default; if already `enabled`, `docker-compose.yml`'s existing `restart: unless-stopped` on `backend`/`frontend` is sufficient for the "survives reboot" acceptance criterion, no extra systemd service needed
- [x] If not enabled: `sudo systemctl enable docker`

### 4. Pi — TradingAgents setup
- [x] `sudo mkdir -p /opt/tradingagents && sudo chown $(whoami) /opt/tradingagents`
- [x] `git clone https://github.com/TauricResearch/TradingAgents /opt/tradingagents` (fresh clone, public repo, no auth needed — decided against copying the Mac's existing clone, see `challenges.md`)
- [x] Confirm `docker-compose.yml`'s `backend` service already mounts `/opt/tradingagents:/opt/tradingagents` (it does — no edit needed)

### 5. Pi — bring up the stack
- [x] `docker compose up -d` (from `~/projects/youn-server`) — starts/updates `backend`, `frontend`, and re-confirms `pihole` (already running from `#34`, shouldn't be disrupted)
- [x] `docker compose ps` — confirm all three containers show `Up`/healthy, no restart loops
- [x] `docker compose logs backend --tail 50` — check for startup errors, especially DB connection failures

### 6. Pi — build TradingAgents' venv inside the container
- [x] `docker compose exec backend python -m venv /opt/tradingagents/.venv`
- [x] `docker compose exec backend /opt/tradingagents/.venv/bin/pip install -r /opt/tradingagents/requirements.txt`
- [x] `docker compose exec backend /opt/tradingagents/.venv/bin/python -c "import tradingagents"` — smoke test, confirms the venv actually works
- [x] No Docker Desktop File Sharing step needed here (that was Mac-only, per the issue's existing note) — Pi's plain Docker Engine has no such restriction

### 7. Verify DB migrations are current
- [x] Since the Pi's `backend` connects to the *same* NAS DB local dev has already been using (not a fresh database), check whether anything's pending rather than assuming: `docker compose exec backend alembic current` vs `docker compose exec backend alembic heads` — should match; if not, `docker compose exec backend alembic upgrade head`
- [x] No auto-migration exists in `main.py`'s `lifespan` (confirmed during planning) — this has to be a manual check/step, not something the container does for you on startup

### 8. Testing & Validation
- [x] `GET /api/health` reachable from iPhone over Tailscale (Tailscale IP, off home Wi-Fi)
- [ ] ~~Trigger a real stock alert / `POST /api/poll/stocks`, confirm Pushover push received on iPhone, iPad, Mac (Apple Watch via standard iOS mirroring)~~ — substituted with a generic Pushover API test instead (direct `curl` to `api.pushover.net`, no real alert threshold crossed): confirmed push delivery infra works end-to-end (Pi → Pushover → iPhone, including the first-unlock-after-reboot decrypt quirk). The real alert didn't fire because Finnhub's REST quote 403'd on `RY.TO` (non-US ticker, unsupported on Finnhub's free tier) — unrelated to Pi/Tailscale/Pushover. Real stock-alert-triggered push remains untested; see explicit note on `#13`'s own acceptance criteria in `issues.md`
- [ ] ~~`POST /api/stockalerts/{id}/analyze` on a real alert, confirm `status`: `pending → running → done`~~ — **deferred to `#42`**: checking runtime config before attempting this found no LLM API key provisioned on the Pi (`.env` only has `FINNHUB_API_KEY`), plus unresolved report migration/storage questions
- [x] `sudo reboot` the Pi, wait for it to come back, confirm `docker compose ps` shows both containers back up automatically with no manual `docker compose up` re-run

### 9. Cutover — retire local dev against the real DB
- [x] Once the above all passes, stop running local `uvicorn` against the NAS DB (per the scheduler double-fire risk in `challenges.md`) — any further local backend dev should use `docker-compose.local.yml`'s throwaway Postgres instead
- [x] Remove the dev Mac's `/opt/tradingagents` symlink if it still exists: `ls -la /opt/tradingagents` to check, `sudo rm /opt/tradingagents` if it's a symlink (per the issue's existing cleanup note — local dev-only scaffolding, not needed once the Pi is primary) — real data untouched, still at `/Users/youn/Documents/tools/TradingAgents` for `#42` to migrate later
- [x] Deleted the local `youn-server-db-1` throwaway container (+ volume) since local dev against it isn't happening yet either — `docker-compose.local.yml` recreates it fresh whenever local dev resumes

### 10. Cleanup
- [x] Update `.doc/issues.md`: mark `#13` done
