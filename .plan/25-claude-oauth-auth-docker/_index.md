# #25: Claude OAuth Auth Working in Docker

## Workflow
No branch/PR — project convention is direct commits to `main` (solo project, no PR review; see [[project-local-dev-workflow]]).

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ⬜ Not started | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] `${HOME}/.config/anthropic/` is mounted into the backend container in `docker-compose.yml`
- [ ] A test call via a bare `Anthropic()` client succeeds from inside the container with no `ANTHROPIC_API_KEY` env var set
- [ ] `anthropic_api_key` removed from `backend/app/core/config.py`

## Estimated Effort
- Implementation: **0.5h**
- Verification (Docker rebuild + exec check, both machines): **0.5h**
- **Total: ~1h** (matches issue estimate)
