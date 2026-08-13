# #13.1: Context

## Issue Description

Off the home LAN, the backend can't reach Postgres: `DATABASE_URL` points at
`<nas-ip>:5433` (the Synology NAS's LAN IP, `#1.5`), which isn't routable
outside the home network. Tailscale is already installed and joined on both
the dev Mac (`<dev-mac-name>`, `<dev-mac-tailscale-ip>`) and the Pi
(`youn-server`, `<pi-tailscale-ip>`) per `#13`'s provisioning note, but that only
makes the Pi itself reachable — it doesn't make the NAS (a separate physical
device on the same LAN as the Pi, not itself a Tailscale node) reachable
through it. Confirmed via direct `asyncpg.connect()` attempts to both
`<nas-ip>:5433` and `<pi-tailscale-ip>:5433` (Pi's Tailscale IP) — both refuse
the connection when off-LAN, since neither routes to the NAS.

Enabling **Tailscale subnet routing** on the Pi — advertising a route to the
NAS's IP through the Pi — solves this: the Pi already sits on the same LAN as
the NAS, so it can forward tailnet traffic to `<nas-ip>` once configured as
a subnet router.

This is scoped as `#13.1`, a sub-issue of `#13` (Pi Deployment + Tailscale).
`#13` itself covers deploying the actual `docker compose up -d` application
stack to the Pi — that work is unrelated and unblocked by this: `#13.1` is
purely about dev-machine reachability to the NAS while off-LAN, independent
of whether the Pi's containers are running.

## Component / Route Summary

### Current State
- `backend/app/core/config.py`'s `Settings.database_url` reads `DATABASE_URL`
  from `.env`, currently `postgresql+asyncpg://youn:...@<nas-ip>:5433/youn_server`.
- Tailscale is installed and joined on the Pi and dev Mac (not on the NAS —
  Synology DSM has no first-party Tailscale package in use here).
- The Pi is not currently advertising any subnet routes — confirmed no
  `tailscale status` output showing a route, and NAS unreachable from a
  Tailscale-only path.
- NAS `pg_hba.conf` currently allows `host youn_server youn 0.0.0.0/0 md5`
  (per `#1.5`'s setup steps) — a TODO left in that issue's notes to
  "restrict to Pi LAN IP once known" was never followed up on.

### Target State
- Pi advertises `<nas-ip>/32` (NAS only, not the full `/24` — see
  `challenges.md` for the security reasoning) as a Tailscale subnet route,
  persisted via `tailscale set --advertise-routes=...` so it survives reboots.
- Route is approved once in the Tailscale admin console.
- Pi has `net.ipv4.ip_forward=1` set persistently (required for any Tailscale
  subnet router to actually forward packets, not just accept the
  advertisement).
- Dev Mac has "Accept subnet routes" enabled in its Tailscale client.
- NAS `pg_hba.conf` is tightened to `<lan-subnet>/24` (the Pi's LAN subnet —
  Tailscale SNATs subnet-router traffic by default, so Postgres sees the
  connection as coming from the Pi's LAN IP, not the Mac's tailnet IP).
- No application code or `DATABASE_URL` value changes — the whole point is
  that `<nas-ip>:5433` becomes reachable exactly as configured today,
  whether on-LAN or on-tailnet.

## Impact & Risk

### Files Changed
- None in this repo. All changes are external: Pi's `tailscaled` state/systemd
  config, Pi's `/etc/sysctl.d/`, NAS's `pg_hba.conf`, and the Tailscale admin
  console's route-approval state.
- `.doc/issues.md` — mark `#13.1` done and note the closed `pg_hba.conf` TODO
  once verified (small doc edit, not code).

### Dependencies
- **`backend/app/core/db.py`** — unaffected; consumes `settings.database_url`
  as-is, no code path change.
- **NAS PostgreSQL package (DSM)** — `pg_hba.conf` edit and service restart
  happen here, per `#1.5`'s existing procedure.
- **Pi's `tailscaled`** — gains a persisted `--advertise-routes` flag.

### Breaking Changes
None expected for existing on-LAN access: the Pi (`<pi-lan-ip>`) and any
other LAN client already fall inside `<lan-subnet>/24`, so tightening
`pg_hba.conf` to that subnet doesn't remove access for anything currently
working. Verify this explicitly during testing (see `implementation.md`)
since it's the one step capable of accidentally locking out existing access
if the subnet is entered incorrectly.
