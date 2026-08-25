# #25: Challenges & Notes

## Potential Challenges

1. **Container UID 1000 may have no home dir in the base image** — `mcr.microsoft.com/playwright/python:v1.62.0-jammy` isn't a project file, so this can't be confirmed by reading the repo; it needs a live `docker exec` check (see implementation.md step 1). Mitigation: set `HOME` explicitly in the Dockerfile if the check comes back empty — removes the dependency on the base image's own `/etc/passwd` entirely, and survives future base-image bumps.

2. **`ANTHROPIC_API_KEY` may already be present (even if empty) in the container env** — the backend service uses `env_file: .env`, and `.env.example` declares `ANTHROPIC_API_KEY=` for TradingAgents' subprocess (Group 4, unrelated to this feature). An empty-string env var is still "present" to some credential-resolution logic. The acceptance criterion is "no `ANTHROPIC_API_KEY` env var set" — if it's present-but-empty during verification, confirm the SDK's resolution order still falls through to the mounted OAuth profile rather than erroring on an empty key; if not, verify with the var explicitly unset for that one check (`env -u ANTHROPIC_API_KEY`) rather than editing `.env`.

3. **`${HOME}` interpolation depends on how `docker compose` is invoked** — if it's ever run via `sudo` or a service manager with a stripped environment, `$HOME` may not be the expected user's home dir. Low risk here (Pi and Mac both run `docker compose` interactively as the deploying user per [[project-local-dev-workflow]]), but worth a sanity echo (`echo $HOME`) on both machines before relying on it, not just after — bad interpolation would mount into an unexpected or non-existent host path instead of failing loudly.

4. **Rebuild required on both machines** — a Dockerfile change (if needed) and a `requirements.txt` change both require `docker compose build backend` before the compose/env changes take effect; a stale image would look like the mount "didn't work" when it's actually just running old code. Confirm rebuild before troubleshooting the mount itself.

5. **OAuth refresh tokens hard-expire, not tied to usage** — the mounted credentials aren't permanent. They don't slide with active use, so even daily chat traffic doesn't delay expiry, and there's no advance warning — the container just starts failing auth one day. Fix when it happens is a re-run of `ant auth login --no-browser` on the affected host (Pi headless via device-code flow), no code change or rebuild needed. Out of scope for #25 itself, but the failure mode has no operator-visible signal until #49 (Pushover alert on `AuthenticationError`) ships — until then, a silent auth failure could sit unnoticed.

## Key Differences

| Aspect | Current (TradingAgents mount) | Target (OAuth mount, this issue) |
|--------|-------------------------------|-----------------------------------|
| Why Mac needs different handling | Two genuinely different real paths (`/opt/tradingagents` vs `/Users/.../TradingAgents`) — no formula connects them | Same conceptual path (user's home dir), different value per host — `${HOME}` interpolation covers it in one line |
| Where the override lives | `docker-compose.local.yml` (explicit second entry) | Nowhere — single line in `docker-compose.yml` |
| Auth mechanism | N/A (not an API-auth concern) | OAuth/Pro-plan (`ant auth login`), replacing the never-wired `anthropic_api_key` API-key field |

## Rollback Plan

1. Revert the `docker-compose.yml` volume line, `backend/Dockerfile` `ENV HOME` line (if added), `backend/requirements.txt` addition, and `backend/app/core/config.py` deletion — straight `git revert` of the single commit, since this is a solo/no-branch project (see [[project-local-dev-workflow]])
2. `docker compose build backend && docker compose up -d backend` on each affected host (Pi, and Mac if the change was tested there) to confirm the container returns to its pre-change state
3. No DB migration or data involved — nothing else to unwind
