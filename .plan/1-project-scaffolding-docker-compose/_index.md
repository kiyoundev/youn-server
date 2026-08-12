# Issue #1: Project Scaffolding + Docker Compose

## PR / Branch
- **Branch:** `feature/1-project-scaffolding-docker-compose`
- **PR Title:** `main | feature - 1 - Project Scaffolding + Docker Compose`

## Task Status

| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ✅ Done | [review.md](review.md) |

## Success Criteria

- [x] `docker compose up` starts both services without error on ARM64
- [x] `backend/` Python project installs cleanly with `pip install -r requirements.txt`
- [x] `frontend/` Next.js app starts at `localhost:3000`
- [x] `.env.example` contains all required keys with placeholder values
- [x] Docker image does not contain `.env` (verified via `docker inspect`)
- [x] Both containers run as UID 1000, not root

## Estimated Effort
- Implementation: **2.5 hours**
- Validation (docker build + compose up on ARM64): **0.5 hours**
- **Total: ~3 hours**


## Git Commit Message

```
Add: initial project scaffolding and Docker setup

Why:
Bootstrap monorepo structure so backend and frontend can be
developed and deployed consistently on Raspberry Pi ARM64.

How:
- Add FastAPI backend skeleton with package structure for api,
  core, models, services, consumers, and scheduler
- Add Next.js 14 App Router frontend with Tailwind, standalone
  output mode for Docker multi-stage build
- Add Dockerfiles for both services using ARM64-compatible base
  images (playwright/python for backend, node:20-alpine for
  frontend)
- Add 'docker-compose.yml' with ARM64 platform, env_file, SQLite
  volume mount, and restart policy
- Add '.env.example' with all required keys documented
- Add '.gitignore' excluding .env, db.sqlite, build artifacts

Tags:
scaffolding, docker, fastapi, nextjs
```