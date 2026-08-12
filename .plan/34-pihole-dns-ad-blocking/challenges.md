# #34: Challenges & Notes

## Potential Challenges

0. **IPv6 DNS bypasses Pi-hole (accepted, not fixed).** The Pi's IPv6
   addresses on the LAN are all dynamic/privacy-extension addresses
   (rotate over time), so none were safe to pin into Eero's Custom DNS
   IPv6 fields — those were left blank/default. Any device that prefers
   IPv6 for DNS lookups will skip Pi-hole and use Eero's normal
   (unfiltered) upstream for those specific queries. In practice most
   traffic still resolves via IPv4 DNS even on dual-stack networks, so
   this is a minor, accepted gap rather than a blocker — revisit only if
   it proves noticeable (e.g. persistent ads on a device known to prefer
   IPv6).

1. **Port 53 conflict with `systemd-resolved`** — ~~Debian/RPi OS binds a
   stub DNS listener by default.~~ **Resolved during implementation
   (2026-08-10):** checked with `ss -tulpn` on the actual Pi —
   `systemd-resolved` is `inactive` (Tailscale manages `/etc/resolv.conf`
   directly) and nothing else is bound to port 53. No host-level fix was
   needed; this was a preemptive risk that didn't materialize on this
   specific setup.

2. **Whole-network DNS outage if misconfigured** — Because the plan
   points the *router's* DHCP DNS setting at the Pi (not just one
   device), a Pi-hole crash, container restart loop, or Pi reboot with
   Docker not auto-starting would take down DNS resolution for the
   entire LAN, not just ad blocking. Mitigation: `restart:
   unless-stopped` plus confirming Docker itself is enabled to start on
   boot (`systemctl is-enabled docker` — already true per the Docker
   install script's default). Keep the Eero's own upstream DNS
   (1.1.1.1/8.8.8.8) configured as Pi-hole's *upstream* resolver so
   Pi-hole itself has a fallback path, and know the rollback (below) to
   quickly point the router back at a public DNS if the Pi goes down.

3. **YouTube ads will not be blocked** — Already documented in
   `context.md` as an accepted limitation, not a defect. Flagging again
   here so it isn't reported as a bug during verification. Both Pi-hole
   and AdGuard Home share this limitation; it's inherent to DNS-level
   blocking, not a Pi-hole shortcoming.

4. **Default blocklist gap vs. AdGuard Home** — Pi-hole's out-of-box
   block rate is slightly lower than AdGuard Home's due to default list
   choice. Mitigation: add hagezi or oisd as a supplemental list on
   first run (implementation step 3) rather than relying on
   StevenBlack alone.

5. **DHCP lease renewal delay during verification** — Existing devices
   on the network won't pick up the new DNS server until their DHCP
   lease renews (could be hours). Mitigation: manually renew/release the
   lease on the test device (or toggle Wi-Fi off/on) rather than waiting,
   and note that the rest of the network will pick it up gradually
   rather than instantly.

## Key Differences
| Aspect | Current | Target |
|--------|---------|--------|
| DNS resolution | Devices use Eero's default upstream DNS directly | Devices use Pi-hole as resolver, which filters then forwards to upstream DNS |
| Docker services on Pi | `backend`, `frontend` only | `backend`, `frontend`, `pihole` |
| Pi LAN IP | Dynamic (DHCP, unreserved) | Reserved/static in Eero |
| Ad blocking | None (per-device browser extensions only, if any) | Network-wide at the DNS layer, except YouTube in-video ads |

## Rollback Plan
1. In the Eero app, revert the DHCP DNS setting back to "Automatic"
   (or the previous custom value) — this is the fastest fix and restores
   DNS for the whole network within one DHCP renewal cycle.
2. Stop the container if needed: `docker compose stop pihole` (leaves
   `backend`/`frontend` untouched since they're independent services).
3. Verify a test device can resolve normal domains again after the DHCP
   setting reverts and its lease renews.
4. If the `pihole` service block needs to be fully removed from the
   repo, `git revert` the commit that added it — no migrations or app
   data are affected since Pi-hole is fully isolated from
   `backend`/`frontend`/Postgres.
