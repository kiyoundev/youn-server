# #25: Context

## Issue Description

Makes Pro-plan/subscription auth (via `ant auth login`) actually usable from inside the backend's Docker container, and removes the dead API-key config that was never wired up.

- Mount `~/.config/anthropic/` (the OAuth profile `ant auth login` creates on the host) into the backend service in `docker-compose.yml` — same pattern already used for TradingAgents' `/opt/tradingagents` volume
- Verify a bare `Anthropic()` client call succeeds *from inside the running container*, with no `ANTHROPIC_API_KEY` set anywhere — confirms the mounted profile is actually being picked up, not just working coincidentally on the host
- Delete `anthropic_api_key` from `backend/app/core/config.py` — declared but has zero usages anywhere in the backend; leaving it in place implies a code path that doesn't exist and invites accidentally wiring up metered API-key billing instead of the intended Pro-plan auth

**Acceptance criteria:**
- [ ] `${HOME}/.config/anthropic/` is mounted into the backend container in `docker-compose.yml`
- [ ] A test call via a bare `Anthropic()` client succeeds from inside the container with no `ANTHROPIC_API_KEY` env var set
- [ ] `anthropic_api_key` removed from `backend/app/core/config.py`

Isolated infra step ahead of #26 (per-report chat backend) — lets #26 be built and tested against working auth from the start, instead of debugging chat logic and auth plumbing at the same time.

## Component / Route Summary

### Current State
- `backend/app/core/config.py` declares `anthropic_api_key: str = ""` — confirmed zero usages anywhere in the backend (only `stock_alert.anthropic_effort`, a *different*, already-wired field for TradingAgents' subprocess LLM config, matches on the same substring)
- `.env.example`'s `ANTHROPIC_API_KEY` is unrelated: `trading_agents.py:22` does `env = os.environ.copy()` and forwards the container's full env straight into the TradingAgents subprocess — it never goes through `Settings`. This entry stays; it belongs to Group 4 (AI Analysis), not this feature.
- `backend/requirements.txt` has no `anthropic` package
- `backend/Dockerfile` runs the app as UID 1000 (`USER 1000`), no `HOME` set explicitly — base image is `mcr.microsoft.com/playwright/python:v1.62.0-jammy`; whether that UID has a home dir in the base image's `/etc/passwd` is unconfirmed (needs a live check, not derivable from the repo)
- `docker-compose.yml` mounts `/opt/tradingagents` for the backend service (Pi path); `docker-compose.local.yml` overrides that one mount to a `/Users/...` path for Mac, since `/opt` isn't in Docker Desktop's default file-sharing list — that override exists because Pi and Mac have two *unrelated* real paths, not a per-user-home difference
- No OAuth profile currently mounted at all — a bare `Anthropic()` client call from inside the container today has no credentials to find

### Target State
- `backend/Dockerfile`: `HOME` set explicitly (exact value TBD — see [implementation.md](implementation.md) step 1), removing dependence on the base image's own `/etc/passwd` entry for UID 1000
- `docker-compose.yml`: one new volume line on the `backend` service, `${HOME}/.config/anthropic:<container-home>/.config/anthropic` — `${HOME}` is Compose env-var interpolation, resolved from whichever host runs `docker compose up`, so it needs no Mac-specific override in `docker-compose.local.yml`
- `backend/requirements.txt`: `anthropic` package added
- `backend/app/core/config.py`: `anthropic_api_key` field deleted
- A bare `Anthropic()` client call succeeds from inside the running container with no `ANTHROPIC_API_KEY` set — verified via a throwaway `docker compose exec` check, not a persisted script (the real client code lands with #26 shortly after)

## Impact & Risk

### Files Changed
- **`backend/Dockerfile`** — add explicit `ENV HOME=...` for UID 1000
- **`docker-compose.yml`** — add OAuth profile volume mount to `backend` service
- **`backend/requirements.txt`** — add `anthropic` package
- **`backend/app/core/config.py`** — remove dead `anthropic_api_key` field

### Dependencies
- **`ant auth login`** (host-side, both Pi and Mac) — must already be run on each host for the mount to have anything to see; this issue doesn't automate that step, it only wires the container up to see it
- **[[project-local-dev-workflow]]** — two-compose-file split; this change only touches the base file, no `docker-compose.local.yml` edit needed under the ${HOME}-interpolation approach

### New Dependencies
- **`anthropic`** (Python package) — needed to make the verification call in this issue, and by #26 immediately after for the real chat endpoint

### Breaking Changes
None — `anthropic_api_key` has zero usages, so removing it doesn't affect any running code path. `.env`/`.env.example` are untouched (the `ANTHROPIC_API_KEY` entry there belongs to TradingAgents' subprocess env, a separate mechanism).
