# Issue #1: Context

## Issue Description

Create the full monorepo directory structure and bootstrap both sub-projects. Wire Docker Compose for ARM64 Pi deployment with correct base images.

**Blocked by:** None — start here.

**Acceptance criteria:**
- `docker compose up` starts both services without error on ARM64
- `backend/` Python project installs cleanly with `pip install -r requirements.txt`
- `frontend/` Next.js app starts at `localhost:3000`
- `.env.example` contains all required keys with placeholder values
- Docker image does not contain `.env`
- Both containers run as UID 1000, not root

## Component / Route Summary

### Current State

Only `.doc/` exists at the project root. No backend, frontend, Dockerfiles, or compose config.

### Target State

```
youn-server/
├── backend/
│   ├── app/                      # placeholder __init__.py (fleshed out in #2+)
│   ├── requirements.txt          # FastAPI, SQLAlchemy, APScheduler, httpx, playwright, etc.
│   ├── pyproject.toml
│   ├── .python-version           # 3.12
│   └── Dockerfile
├── frontend/
│   ├── src/app/                  # Next.js 14 App Router scaffold
│   ├── package.json
│   └── Dockerfile
├── .doc/                         # already exists
├── .env.example
├── .gitignore
└── docker-compose.yml
```

## Impact & Risk

### Files Created

- **`docker-compose.yml`** — defines `backend` and `frontend` services; ARM64 platform; env_file; volume for SQLite; restart policy
- **`backend/Dockerfile`** — `mcr.microsoft.com/playwright/python:v1.x.x-jammy` base; installs `requirements.txt`; non-root user
- **`frontend/Dockerfile`** — `node:20-alpine` multi-stage (deps → builder → runner); non-root user
- **`backend/requirements.txt`** — all Python deps for the full project (pinned minor versions); uses `patchright` instead of `playwright` + `playwright-stealth`
- **`.env.example`** — documents every env var the system needs
- **`.gitignore`** — excludes `.env`, `db.sqlite`, `.doc/`

### New Dependencies

- **`mcr.microsoft.com/playwright/python`** — Microsoft-maintained image with verified ARM64 Chromium. `patchright` (drop-in Playwright replacement) is installed on top and uses this existing Chromium binary — no separate install needed.
- **`patchright`** — Playwright fork that patches at the CDP level; more effective bot-detection bypass than `playwright-stealth`. Drop-in replacement: same API, swap the import.
- **`node:20-alpine`** — standard lightweight Node base for Next.js
