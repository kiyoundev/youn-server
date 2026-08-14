# #13: Challenges & Notes

## Potential Challenges

1. **Scheduler double-fire if the Pi and local Mac both run against the NAS DB.** `backend/app/main.py`'s `lifespan` starts an APScheduler job (`poll_prices`, every 6h, fires immediately on startup) against the shared NAS Postgres DB. If the Pi's `backend` goes live while the Mac's local `uvicorn` is still also running, both would poll/dispatch concurrently — duplicate scrapes, duplicate `Event` rows, duplicate Pushover pushes. `.doc/issues.md` already notes there's no concurrency guard on the poll endpoint. Mitigation: implementation.md step 9 — stop local `uvicorn` against the real DB once the Pi is verified working; any further local dev uses `docker-compose.local.yml`'s throwaway Postgres instead.

2. **`.env` transfer could reset Pi-hole's admin password.** `#34` already deployed `pihole` from this same `docker-compose.yml` — `PIHOLE_WEBPASSWORD` resolves via Compose's automatic `.env`-file interpolation. If the Mac's `.env` has a different value than what's currently live on the Pi, restarting the stack could reapply a different password (Pi-hole v6 reapplies `FTLCONF_*` vars on each start) and lock out the existing admin session. Mitigation: implementation.md step 2 — diff before overwrite, don't blindly `scp` over it.

3. **No auto-migration on startup.** Confirmed during planning: `main.py`'s `lifespan` never calls `alembic upgrade head`. Since the Pi connects to the *same* NAS DB local dev has already been using (not a fresh database), it's likely already current — but "likely" isn't "confirmed." Mitigation: implementation.md step 7 explicitly checks `alembic current` vs `alembic heads` before assuming.

4. **TradingAgents venv can't be reused across machines.** The Mac's existing local clone's `.venv` is built with Darwin binaries — won't run in the Pi's Linux ARM64 container. Already accounted for: implementation.md step 4 does a fresh `git clone` directly on the Pi rather than copying the Mac's folder, and step 6 builds a fresh venv inside the container regardless.

5. **Repo is private — cloning depends on the deploy key from `#34` still being valid.** Not expected to be an issue (nothing has revoked it since), but if `git pull` in step 1 fails with a permission error, that's the first thing to check (`GitHub → repo → Settings → Deploy keys`) rather than assuming something else broke.

## Key Differences

| Aspect | Current | Target |
|--------|---------|--------|
| Where the app runs | Mac, `uvicorn --reload`, local dev only | Pi, Docker Compose, persistent |
| DB access pattern | Mac only, on/off-LAN via `#13.1`'s route | Pi (on home LAN) + Mac (dev, only via `docker-compose.local.yml` post-cutover) |
| Notification testing | Manual/ad-hoc | Real end-to-end Pushover push from a live deployed instance |
| TradingAgents | Mac-only symlink to local clone | Fresh clone + venv on the Pi, Mac's symlink retired |
| Reboot survival | N/A (Mac dev server) | `docker-compose.yml`'s existing `restart: unless-stopped` + Docker daemon enabled at boot |

## Rollback Plan
1. `docker compose down` on the Pi (stops `backend`/`frontend`; leave `pihole` running if it's unaffected — check first rather than assuming a full `down` is needed).
2. Resume local `uvicorn` against the NAS DB as before, if the Pi deploy needs to be backed out entirely.
3. `.env` on the Pi can stay in place (no secrets need rotating just from a rollback) unless a credential was suspected compromised during the process.
4. Verify Pi-hole (`#34`) still works independently after any `docker compose down`/`up` cycle — it's on its own network, shouldn't be affected, but worth the same regression check `#13.1` used for the NAS side.
