# #34: Context

## Issue Description
Deploy Pi-hole as a new Docker container on the Raspberry Pi (model 4B,
Raspberry Pi OS Lite 64-bit, headless), alongside the existing youn-server
services — added to the same `docker-compose.yml`, exposing DNS (port 53,
TCP+UDP) and the admin web UI.

- New service block in `docker-compose.yml`, `restart: unless-stopped`
  matching the existing services' convention
- Default community blocklists enabled on first run
- **HITL:** confirm the Pi has a reserved LAN IP (Eero app → Devices →
  reserve, same step already done for the NAS)
- **HITL:** point the router's DHCP DNS setting (Eero app) at the Pi's
  LAN IP so every device on the network picks it up automatically

**Tool decision (made during planning):** Pi-hole over AdGuard Home.
AdGuard Home has a slightly better out-of-box block rate (broader default
lists) and built-in DoH/DoT, but Pi-hole has the most prior art for
"Docker on Raspberry Pi" specifically and the gap is closed by adding one
extra list (hagezi or oisd) alongside the default StevenBlack list.

**Known hard limitation (confirmed during planning, not a bug):**
Neither Pi-hole nor AdGuard Home can block YouTube's in-video/pre-roll
ads — YouTube serves ads from the same domains (`googlevideo.com`,
`youtube.com`) as the actual video, so blocking at DNS level would break
playback entirely. This is out of scope for both tools; document it as a
known limitation rather than a defect.

## Component / Route Summary

### Current State
- `docker-compose.yml` at the repo root defines two services: `backend`
  (FastAPI, port 8000) and `frontend` (Next.js, port 3000), both built
  from local Dockerfiles, `platform: linux/arm64`, `restart:
  unless-stopped`, sharing `.env` via `env_file`. No custom Docker
  network is declared — both use the default bridge network with
  host port mappings.
- `docker-compose.local.yml` shows the project's convention for a
  third-party (non-built) image service: pinned image tag, `restart:
  unless-stopped`, environment block, port mapping comment explaining
  *why* that host port was chosen, a healthcheck, and a named volume for
  persistent state. This issue's Pi-hole service should follow that same
  pattern rather than the `build:` pattern used by `backend`/`frontend`.
- The Pi (4B, RPi OS Lite 64-bit) already has Docker + Tailscale
  installed (per recent setup) and is reachable over Tailscale at
  `<pi-tailscale-ip>` in addition to its LAN IP. It does not yet have a
  reserved/static LAN IP in the Eero app.
- Raspberry Pi OS (Debian-based) runs `systemd-resolved` by default,
  which binds a stub resolver to `127.0.0.53:53`. This does **not**
  conflict with a Docker container's `53:53` port mapping on the *host's
  real* LAN IP by default in most cases, but can conflict if
  `systemd-resolved`'s stub listener is also bound to `0.0.0.0:53` or if
  `dnsmasq`/`avahi` is also running — must be verified on this specific
  Pi during implementation (see `challenges.md`).

### Target State
- New `pihole` service added to `docker-compose.yml` using the official
  `pihole/pihole` image (arm64-compatible), with:
  - DNS ports `53/tcp` and `53/udp` mapped to the host
  - Admin web UI on a host port that doesn't collide with
    `frontend` (3000) or `backend` (8000) — proposing `8081`
  - `TZ`, `WEBPASSWORD` (or `FTLCONF_webserver_api_password` for newer
    image versions), and `FTLCONF_dns_listeningMode=all` (or equivalent)
    set via environment/`.env`
  - A named volume for `/etc/pihole` (config + blocklists persistence)
    and `/etc/dnsmasq.d` (custom dnsmasq config), matching the
    `pgdata`-style named-volume convention from `docker-compose.local.yml`
  - `restart: unless-stopped`, no `platform:` pin needed since Pi-hole
    publishes a multi-arch manifest (unlike `backend`/`frontend` which
    build locally and need the explicit `linux/arm64` pin)
- Host-level fix (outside docker-compose, applied directly on the Pi) to
  free port 53 from `systemd-resolved`'s stub listener if it's found to
  conflict.
- Blocklists: default StevenBlack list (ships enabled) + one additional
  list (hagezi "Pro" or oisd "Big") added via the admin UI or `pihole-FTL`
  CLI on first run.
- No changes to `backend`/`frontend` services or the app's own database —
  this is a fully separate, unrelated Docker service sharing only the
  host and compose file.

## Impact & Risk

### Files Changed
- **`docker-compose.yml`** — add the `pihole` service block; no changes
  to existing `backend`/`frontend` services.
- **`.env.example`** — add `PIHOLE_WEBPASSWORD` (or equivalent) as a
  documented optional variable, matching how `POSTGRES_PASSWORD` is
  documented for the local Postgres compose file.
- **`.doc/issues.md`** — check off ACs / update #34 body with the final
  reserved IP and any deviations once done.
- Pi host config (not tracked in this repo) — potential
  `systemd-resolved` config change to free port 53; documented here for
  reproducibility but not committed as a repo file.

### Dependencies
- **Eero app** — manual HITL steps for IP reservation and DHCP DNS
  pointer; no API/automation available for Eero, must be done via the
  mobile app UI.
- **Existing Docker Compose stack on the Pi** — Pi-hole is additive; it
  does not depend on and is not depended on by `backend`/`frontend`.

### New Dependencies
- **`pihole/pihole` Docker image** — official image, arm64 manifest
  available, pin to a specific tag (not `latest`) for reproducibility,
  e.g. `pihole/pihole:2024.07.0` (verify latest stable tag at
  implementation time).

### Breaking Changes
None to the existing app. Risk is entirely at the network layer if the
router's DHCP DNS pointer is misconfigured — see `challenges.md` for the
rollback plan.
