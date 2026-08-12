# Security

## API Authentication

Shared API key via `X-API-Key` header on all routes except `GET /api/health`.

- Key generated at setup: `python -c "import secrets; print(secrets.token_hex(32))"`
- Stored in `.env` as `API_KEY`
- FastAPI dependency applied at router-mount time (see api.md)
- Frontend proxies all requests server-side — key never reaches browser
- iOS app stores key in `UserDefaults` — acceptable for personal single-user app

## Sensitive Files

| File | Permission | Storage |
|------|-----------|---------|
| `.env` | `chmod 600` | Pi host filesystem only; excluded from git via `.gitignore` |
| `db.sqlite` | Default | Pi host filesystem; unencrypted — acceptable for personal use |

Pushover replaces APNs — no `.p8` key file needed. `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` live in `.env`.

## Network

Tailscale (WireGuard) provides encrypted peer-to-peer tunnels between Pi and all Apple devices. Pi is not exposed to the public internet. No port forwarding required.

## Docker

- Backend and frontend containers run as non-root (`USER 1000` in Dockerfiles)
- `.env` file excluded from Docker image build context via `.dockerignore`

## Operational Risks

| Risk | Mitigation |
|------|-----------|
| Pi stolen | SQLite, `.env`, `.p8` all on disk unencrypted — accept risk for home server |
| Tailscale account compromised | Attacker reaches Pi API; API key is second factor |
| Pushover key leak | `PUSHOVER_APP_TOKEN` + `USER_KEY` in `.env` — `chmod 600` mitigates |
| yfinance data | Outbound only, no user data sent |
| Scraping ToS (Amazon) | Legal risk to scraper operator, not a security risk |

## What Is Not Implemented (Intentional)

- No HTTPS on Pi — all traffic is over Tailscale encrypted tunnel; LAN-only access
- No user accounts — single-user personal tool
- No secrets manager — `.env` file is sufficient at this scale
