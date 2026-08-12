# Issue #1: Challenges & Notes

## Potential Challenges

1. **ARM64 Chromium via wrong base image** — Running `patchright install chromium` on a plain Python or Debian ARM64 image can pull binaries that don't match the Pi's glibc version, resulting in a crash at runtime. Use `mcr.microsoft.com/playwright/python` as the base — it bundles verified ARM64 Chromium. `patchright` (installed via pip on top) reuses this Chromium binary.

2. **`docker compose build` on Mac (AMD64) vs Pi (ARM64)** — Building locally on an M-series Mac with `platform: linux/arm64` forces QEMU emulation. Build is slow but functional. For iteration speed, build on the Pi directly or use `docker buildx`. The `platform:` key in compose ensures the Pi runs the correct arch at runtime.

3. **Next.js standalone output** — The `output: 'standalone'` config in `next.config.ts` is required for the Dockerfile's multi-stage runner to work (copies `server.js`). Without it, `node server.js` fails. Confirm this is set before `docker compose build`.

4. **`.env` not baked into image** — `env_file:` in compose passes vars at runtime. Confirm the `backend/Dockerfile` does NOT have a `COPY .env .` line and that `.dockerignore` excludes `.env`. Use `docker history` or `docker inspect` to verify no secret layers exist.

5. **SQLite volume path on Pi** — `./data/db.sqlite` in compose resolves relative to the compose file location. On the Pi, this path must exist before `docker compose up` or Docker creates it as a directory, not a file, breaking SQLite. The `data/` directory with `.gitkeep` handles this; confirm the file exists pre-up.

## Key Differences

| Aspect | Typical Python Docker setup | This project |
|--------|-----------------------------|--------------|
| Base image | `python:3.12-slim` | `mcr.microsoft.com/playwright/python` (includes ARM64 Chromium for patchright) |
| Platform | Default host arch | `linux/arm64` explicit |
| Next.js output | Default (`.next/`) | `standalone` (copies only needed files) |
| DB volume | Postgres container | Host-mounted SQLite file |
