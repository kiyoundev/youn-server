# #13.1: Tailscale Subnet Routing (NAS Postgres Reachability)

## PR / Branch
Not applicable — this is a HITL infra/ops task (Pi SSH commands, Synology DSM config,
Tailscale admin console clicks). No application code changes are required. If the
`pg_hba.conf` tightening step later needs to be reflected in repo docs
(`.doc/issues.md`, `.env.example` comments), those are plain doc edits, not a
feature branch/PR.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] Pi advertises route `<nas-ip>/32` via Tailscale, persisted across reboots
- [ ] Route approved in Tailscale admin console
- [ ] Dev Mac has "Accept subnet routes" enabled and can reach `<nas-ip>:5433`
      while off the home LAN (Tailscale connected)
- [ ] `net.ipv4.ip_forward=1` set persistently on the Pi (survives `sudo reboot`)
- [ ] `backend/.venv/bin/uvicorn app.main:app --reload` starts cleanly off-LAN,
      with `DATABASE_URL` unchanged (still pointing at `<nas-ip>:5433`)
- [ ] NAS `pg_hba.conf` tightened from `0.0.0.0/0` to `<lan-subnet>/24` for the
      `youn_server` database, closing the TODO left open since `#1.5`
- [ ] Existing on-LAN Postgres access (from the Pi, from Mac when on home LAN)
      still works after the `pg_hba.conf` change

## Estimated Effort
- Implementation: **0.5h**
- Testing: **0.25h**
- **Total: ~0.75h**
