# #34: Implementation

## Steps

### 1. Host prep (on the Pi, before touching docker-compose) — ✅ done 2026-08-10
- [x] SSH into the Pi (now passwordless via `~/.ssh/id_ed25519`) and check
      what's bound to port 53: `sudo ss -tulpn | grep ':53'`
- [x] Result: **nothing is bound to port 53.** Only `avahi-daemon` on
      `5353/udp` (mDNS, unrelated), plus `tailscaled`/`sshd`. No conflict.
- [x] `systemd-resolved` is already `inactive` — Tailscale manages
      `/etc/resolv.conf` directly (nameserver `100.100.100.100`,
      MagicDNS). No `DNSStubListener` change needed; skip this sub-step.
- [x] Confirmed Pi's current LAN IP: **`<pi-lan-ip>`** (also reachable via
      Tailscale at `<pi-tailscale-ip>` / `youn-server.local`) — this is the
      IP to reserve in the Eero app in step 4.

### 2. Docker Compose service — ✅ done 2026-08-10 (compose file only; not yet started on the Pi)
- [x] Added a `pihole` service block to `docker-compose.yml`. Verified
      current Pi-hole v6 docs before writing it — `WEBPASSWORD` is
      deprecated in favor of `FTLCONF_webserver_api_password`, and
      bridge networking (no `--net=host`) requires
      `FTLCONF_dns_listeningMode: all`. Skipped `cap_add: NET_ADMIN` —
      that's only needed for DHCP/IPv6-RA, which Pi-hole isn't doing
      here (Eero stays the DHCP server).
      ```yaml
      pihole:
        image: pihole/pihole:2026.05.0
        restart: unless-stopped
        environment:
          TZ: America/Los_Angeles
          FTLCONF_webserver_api_password: ${PIHOLE_WEBPASSWORD}
          FTLCONF_dns_listeningMode: all
        ports:
          - "53:53/tcp"
          - "53:53/udp"
          - "8081:80"
        volumes:
          - pihole_etc:/etc/pihole
      ```
      Pinned to `2026.05.0` (~1 month old at plan time) rather than
      `latest` or the newest tag, per the repo's dependency-pinning
      convention.
- [x] Added `pihole_etc` to the top-level `volumes:` block (only volume
      needed for Pi-hole v6 — the `/etc/dnsmasq.d` volume is legacy,
      only relevant when migrating from v5)
- [x] Added `PIHOLE_WEBPASSWORD` to `.env.example` with a comment on how
      to generate a value; **user still needs to add the real value to
      `.env`** — that file is gitignored/agent-ignored, can't be edited
      by the agent
- [x] `docker compose up -d pihole` and confirm it starts healthy —
      **done 2026-08-10.** Deployment path: committed to
      `feature/34-pihole-dns-ad-blocking`, pushed, cloned onto the Pi at
      `~/projects/youn-server` via a new read-only GitHub deploy key
      (repo wasn't cloned there yet — #13 full deployment hasn't
      happened). Created a minimal `.env` on the Pi with just
      `PIHOLE_WEBPASSWORD` (backend/frontend's real secrets aren't
      needed since only `docker compose up -d pihole` was run, not the
      full stack). Container reached `health: healthy` within ~45s;
      gravity compiled 99,558 domains from the default StevenBlack
      list; verified `dig @<pi-lan-ip> google.com` resolves normally and
      `dig @<pi-lan-ip> doubleclick.net` returns `0.0.0.0` (blocked); admin
      UI returns HTTP 302 (login redirect) at `http://<pi-lan-ip>:8081/`.

### 3. Blocklist configuration — ✅ done 2026-08-10 (via CLI/API, no UI needed)
- [x] Confirmed the default StevenBlack list is present (99,558 domains,
      `status: 1`) via `pihole api lists`
- [x] Added hagezi "Pro" as the supplemental list. Note: `pihole api`
      CLI only supports GET; POST/PUT/DELETE required authenticating
      directly against the local REST API with `curl` inside the
      container (`POST /api/auth` with the webserver password → `sid` →
      `POST /api/lists?type=block`).
      Also note: the canonical `raw.githubusercontent.com/hagezi/
      dns-blocklists/main/hosts/pro.txt` URL from most guides 404s —
      that path was restructured (moved to `/adblock/pro.txt`, and even
      that path seems to intermittently 404 directly from
      `raw.githubusercontent.com`). Used hagezi's jsDelivr CDN mirror
      instead, which resolved reliably:
      `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/pro.txt`
- [x] `pihole -g` (update gravity) — hagezi Pro added 215,439 domains,
      bringing the total to **314,997 unique blocked domains**
- [x] Verified via `dig @<pi-lan-ip>`: `google.com` resolves normally,
      `doubleclick.net` and `googleadservices.com` both return `0.0.0.0`
      (blocked)

### 4. HITL network steps (require the user, not automatable) — ✅ done 2026-08-10
- [x] Reserved the Pi's LAN IP (`<pi-lan-ip>`) in the Eero app
- [x] Pointed Eero's Custom DNS at `<pi-lan-ip>` (IPv4 primary only —
      IPv4 secondary and both IPv6 fields left blank/default, since the
      Pi's IPv6 addresses are dynamic/privacy-extension and unstable to
      pin; accepted as a known minor gap, see `challenges.md`).
      Eero rebooted to apply.
- [x] Confirmed via Pi-hole's `/api/stats/summary` immediately after
      reboot: Eero (`<router-ip>`) is already forwarding queries to
      Pi-hole as the upstream resolver (630 queries, 91 blocked,
      14.4% block rate, 4 active clients) — DHCP DNS change took effect
      without needing a manual per-device renew

### 5. Verification — ✅ done 2026-08-10
- [x] Ran `https://adblock.turtlecute.org` (maintained fork; the
      ticket's originally-suggested `d3ward.github.io/toolset` is
      archived/dead) on a real Wi-Fi-connected device: **128/132
      blocked (97%)** — Amazon/Doubleclick/Google Ads/Google Analytics/
      Facebook/TikTok/etc. all correctly blocked. The handful of misses
      are compatibility/cosmetic-filter checks that DNS-level blocking
      structurally can't catch (not a Pi-hole config issue)
- [x] Confirmed normal sites/apps (email, bank, news) load normally on
      the same device — no false-positive breakage
- [x] Pi-hole dashboard confirmed showing live query traffic from LAN
      (via Eero's proxied queries, per the note in step 4)
- [ ] YouTube-ads-still-play check — not explicitly re-verified after
      the DHCP switch, but expected to be unaffected per the documented
      limitation (YouTube ads share domains with video content)

### 6. Cleanup / docs — ✅ done 2026-08-10
- [x] Updated `.doc/issues.md` #34 with final admin port (8081),
      reserved IP (`<pi-lan-ip>`), blocklists added (StevenBlack + hagezi
      Pro), corrected Pi model (4B not 5), corrected dead test-page link
      (turtlecute fork instead of archived d3ward), and checked off all
      ACs; summary table row updated to ✅ Done
- [x] Confirmed `.env.example` documents `PIHOLE_WEBPASSWORD=change_me`
      — placeholder only, no real secret value
