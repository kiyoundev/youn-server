# #34: DNS-Based Ad Blocking (Pi-hole)

## PR / Branch
- **Branch:** `feature/34-pihole-dns-ad-blocking`
- **PR Title:** `main | feature - 34 - Pi-hole DNS ad blocking`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [x] Pi-hole container running on the Pi, added to `docker-compose.yml` alongside `backend`/`frontend`, `restart: unless-stopped`
- [x] `systemd-resolved` checked — was already inactive (Tailscale manages `resolv.conf`), no fix needed, port 53 was free
- [x] Admin web UI reachable on the LAN at `http://<pi-lan-ip>:8081/admin`
- [x] Default blocklists (StevenBlack, 99,558 domains) + hagezi Pro (215,439 domains) enabled — 314,997 total unique domains blocked
- [x] **HITL:** Pi's LAN IP (`<pi-lan-ip>`) reserved in the Eero app
- [x] **HITL:** Eero's Custom DNS points at `<pi-lan-ip>` (IPv4 only, IPv6 left default — see `challenges.md`)
- [x] Ad-serving test page shows ads blocked on a test device — `https://adblock.turtlecute.org` (d3ward's original link is archived/dead): **128/132 blocked (97%)**
- [x] Normal (non-blocked) domains still resolve correctly on that test device — no DNS breakage
- [x] Known limitation documented: YouTube in-video ads are NOT blocked (ads share `googlevideo.com`/`youtube.com` with content — blocking would break playback)
- [x] `.doc/issues.md` #34 checked off / updated with final IP and deviations from plan (Pi model corrected 4B not 5, AdGuard Home not used, dead test-page link fixed)

## Estimated Effort
- Implementation: **~45 min** (compose service + host port-53 fix + blocklist config)
- HITL steps (Eero reservation + DHCP DNS pointer) + manual verification: **~20 min**
- **Total: ~1h** (matches ticket's original estimate)
