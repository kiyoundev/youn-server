# #25: Implementation

## Steps

### 1. Investigate container HOME (Pi, since that's where it'll actually run)
- [ ] `docker compose exec backend sh -c 'echo $HOME; whoami; id'` — confirm whether UID 1000 already has a home dir from the base image, and what it is
- [ ] Decide the container-side mount target based on the result:
  - If a sane `$HOME` already exists (e.g. `/home/pwuser`) — use it as-is
  - If `$HOME` is empty/`/` or UID 1000 has no `/etc/passwd` entry — add `ENV HOME=/home/appuser` (or similar) to `backend/Dockerfile` so the target path is explicit and stops depending on the base image's own user table

### 2. Dockerfile (only if step 1 found no usable HOME)
- [ ] Add `ENV HOME=/home/appuser` (adjust name if it collides with anything in the base image) to `backend/Dockerfile`, before `USER 1000`
- [ ] Rebuild (`docker compose build backend`) and re-run the step 1 check to confirm `$HOME` now resolves as expected

### 3. docker-compose.yml
- [ ] Add to `backend.volumes`:
  ```yaml
  - ${HOME}/.config/anthropic:${CONTAINER_HOME}/.config/anthropic
  ```
  (with `${CONTAINER_HOME}` replaced by the literal path from step 1/2 — Compose only interpolates `${HOME}` from the *host* env, not a container-side variable, so the right-hand side must be a literal string)
- [ ] No `docker-compose.local.yml` change — `${HOME}` interpolates per-host automatically (`/home/youn` on Pi, `/Users/youn` on Mac), and `/Users/...` is already in Docker Desktop's default file-sharing list

### 4. Backend dependency
- [ ] Add `anthropic` to `backend/requirements.txt` (pick current stable version range; check `pip index versions anthropic` or PyPI at implementation time rather than trusting a training-data version number)
- [ ] Rebuild the backend image so the package is installed

### 5. Config cleanup
- [ ] Remove `anthropic_api_key: str = ""` from `backend/app/core/config.py`
- [ ] Grep the backend once more for `anthropic_api_key` post-removal to confirm no stray reference was missed

### 6. Verification (both machines the app actually runs on: Pi, and Mac if used for local dev)
- [ ] Confirm `ant auth login` has been run on the host (Pi and/or Mac) — this issue assumes it, doesn't automate it
- [ ] `docker compose exec backend python -c "from anthropic import Anthropic; c = Anthropic(); print(c.messages.create(model='claude-opus-5', max_tokens=16, messages=[{'role':'user','content':'say hi'}]))"` with `ANTHROPIC_API_KEY` confirmed unset in the container env (`docker compose exec backend sh -c 'echo $ANTHROPIC_API_KEY'` should print nothing — note: it may still be inherited from the TradingAgents `.env` entry via `env_file: .env` on the backend service; if so, temporarily comment it out for this one check or explicitly `env -u ANTHROPIC_API_KEY` the exec command, then confirm the call still succeeds via the mounted OAuth profile)
- [ ] Throwaway check only — no new file committed for this (per confirmed decision; #26 will add real, tested chat code shortly after)

### 7. Cleanup
- [ ] Remove any temporary `ENV HOME` naming experiments if step 1 turned out not to need a Dockerfile change
- [ ] Double check `.env` / `.env.example` were **not** touched — the `ANTHROPIC_API_KEY` entry there is for TradingAgents' subprocess, out of scope here
