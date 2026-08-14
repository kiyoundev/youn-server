# #13: Pi Deployment + Tailscale

## PR / Branch
Not applicable — this is a HITL infra/ops task (Pi SSH commands, app installs, `docker compose up`). No application code changes are required beyond what `#13.1`/`#13.2` already shipped. If anything unexpected needs a code fix mid-deploy, that becomes its own small follow-up issue/branch rather than retrofitted here.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] Pi and all Apple devices appear in Tailscale dashboard with stable IPs
- [ ] `docker compose up -d` starts both containers on Pi without error
- [ ] Containers restart automatically after `sudo reboot`
- [ ] `.env` has `chmod 600`
- [ ] `GET /api/health` reachable from iPhone over Tailscale (Tailscale IP)
- [ ] Pushover push notification received on iPhone, iPad, Mac, and Apple Watch
- [ ] PostgreSQL on NAS reachable from Pi after `docker compose restart` (verify via `GET /api/health`)
- [ ] `docker compose exec backend /opt/tradingagents/.venv/bin/python -c "import tradingagents"` succeeds
- [ ] `POST /api/stockalerts/{id}/analyze` on a real alert completes end-to-end (`status`: `pending → running → done`)

## Estimated Effort
- Implementation: **2h**
- Testing: **1h**
- **Total: ~3h** (matches original issue estimate)
