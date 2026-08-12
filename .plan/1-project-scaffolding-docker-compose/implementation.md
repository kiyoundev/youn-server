# Issue #1: Implementation

## Steps

### 1. Root scaffold

- [ ] Create `.gitignore` — exclude `.env`, `db.sqlite`, `.plan/`, `__pycache__/`, `.next/`, `node_modules/`
- [ ] Create `.env.example` with all keys and placeholder values:
  ```
  API_KEY=change_me
  PUSHOVER_APP_TOKEN=
  PUSHOVER_USER_KEY=
  GMAIL_USER=
  GMAIL_APP_PASSWORD=
  FINNHUB_API_KEY=
  CORS_ORIGINS=http://localhost:3000
  DATABASE_URL=sqlite+aiosqlite:///./db.sqlite
  ```

### 2. Backend scaffold

- [ ] Create `backend/.python-version` — `3.12`
- [ ] Create `backend/pyproject.toml` — project name, Python requires `>=3.12`
- [ ] Create `backend/requirements.txt` — pin all deps:
  ```
  fastapi>=0.111,<0.112
  uvicorn[standard]>=0.29
  sqlalchemy[asyncio]>=2.0
  aiosqlite>=0.20
  alembic>=1.13
  apscheduler>=3.10
  httpx[http2]>=0.27
  beautifulsoup4>=4.12
  patchright>=1.44
  yfinance>=0.2
  pydantic-settings>=2.2
  python-multipart>=0.0.9
  ```
- [ ] Create `backend/app/__init__.py` — empty; marks package
- [ ] Create `backend/app/main.py` — minimal FastAPI app: `GET /api/health` returning `{"status": "ok"}`; confirms server starts
- [ ] Create `backend/Dockerfile`:
  ```dockerfile
  FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  RUN useradd -m -u 1000 appuser && chown -R appuser /app
  USER appuser
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

### 3. Frontend scaffold

- [ ] Run `npx create-next-app@14 frontend --typescript --tailwind --app --no-git --no-eslint` from project root
- [ ] Trim generated boilerplate from `src/app/page.tsx` — replace with placeholder "youn-server dashboard"
- [ ] Create `frontend/Dockerfile` — multi-stage:
  ```dockerfile
  FROM node:20-alpine AS deps
  WORKDIR /app
  COPY package*.json ./
  RUN npm ci

  FROM node:20-alpine AS builder
  WORKDIR /app
  COPY --from=deps /app/node_modules ./node_modules
  COPY . .
  RUN npm run build

  FROM node:20-alpine AS runner
  WORKDIR /app
  ENV NODE_ENV=production
  RUN addgroup -g 1000 appgroup && adduser -u 1000 -G appgroup -s /bin/sh -D appuser
  COPY --from=builder /app/.next/standalone ./
  COPY --from=builder /app/.next/static ./.next/static
  COPY --from=builder /app/public ./public
  USER appuser
  EXPOSE 3000
  CMD ["node", "server.js"]
  ```
- [ ] Add `output: 'standalone'` to `next.config.ts` (required for the standalone Docker build)

### 4. Docker Compose

- [ ] Create `docker-compose.yml`:
  ```yaml
  services:
    backend:
      build: ./backend
      platform: linux/arm64
      restart: unless-stopped
      env_file: .env
      ports:
        - "8000:8000"
      volumes:
        - ./data/db.sqlite:/app/db.sqlite

    frontend:
      build: ./frontend
      platform: linux/arm64
      restart: unless-stopped
      env_file: .env
      ports:
        - "3000:3000"
      depends_on:
        - backend
  ```
- [ ] Create `data/` directory with `.gitkeep` — Docker volume mount target for SQLite file

### 5. Validation

- [ ] `docker compose build` — confirm both images build without error
- [ ] `docker compose up` — confirm `GET http://localhost:8000/api/health` returns `{"status": "ok"}`
- [ ] Confirm `GET http://localhost:3000` renders placeholder page
- [ ] `docker inspect youn-server-backend-1 | grep -i env` — confirm `.env` values not baked in; confirm `API_KEY` not visible in image layers
- [ ] `docker exec youn-server-backend-1 id` — confirm UID 1000
- [ ] `docker exec youn-server-frontend-1 id` — confirm UID 1000

### 6. Cleanup

- [ ] Remove any Next.js boilerplate files not needed (default `globals.css` vars, demo page content)
- [ ] Confirm `.gitignore` covers `data/db.sqlite`, `.env`, `.plan/`, `node_modules/`, `.next/`
