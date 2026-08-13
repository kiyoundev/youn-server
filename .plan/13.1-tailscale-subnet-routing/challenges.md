# #13.1: Challenges & Notes

## Potential Challenges

1. **Route scope: `/24` vs `/32`** — advertising the full `<lan-subnet>/24` LAN
   is the more common Tailscale tutorial default and requires no future
   config changes if another LAN device needs remote reachability later.
   Scoping to `<nas-ip>/32` (NAS only) is more restrictive: a compromised
   device anywhere on the tailnet only gets a path to the Postgres port on
   the NAS, not to the whole home network (other NAS shares, IoT devices,
   router admin UI). Chosen: `/32`, prioritizing least-privilege since there
   is exactly one concrete reachability need today. Mitigation if another
   device needs reaching later: re-run `tailscale set` with an additional
   `/32` entry and re-approve in the admin console — cheap to extend.

2. **SNAT behavior changing the source IP Postgres sees** — Tailscale's
   subnet router SNATs traffic by default, so connections arriving at the
   NAS appear to originate from the Pi's LAN IP (`<pi-lan-ip>`), not the
   originating tailnet device's IP (e.g. the Mac's `<dev-mac-tailscale-ip>`). This
   is *why* tightening `pg_hba.conf` to `<lan-subnet>/24` (which covers the
   Pi's LAN IP) works, rather than needing the Mac's Tailscale CGNAT range
   (`100.64.0.0/10`) allowlisted instead. Verify this assumption holds by
   testing — if a connection attempt from off-LAN is unexpectedly rejected
   after the `pg_hba.conf` change, check the NAS's Postgres log for what
   source IP it's actually seeing (`pg_hba.conf` rejections are logged) and
   adjust the CIDR listed rather than assuming SNAT is broken.

3. **`pg_hba.conf` typo locking out existing access** — this is the one step
   in this issue capable of an outage (backend on the Pi loses DB access if
   the subnet is wrong). Mitigated by the explicit on-LAN regression check
   in `implementation.md` step 6, and by the rollback plan below being a
   one-line revert.

4. **Forgetting IP forwarding persistence** — `sysctl -w` changes are
   session-only; if only that's run (not the `/etc/sysctl.d/` file), the
   route will silently stop forwarding packets after the next Pi reboot even
   though `tailscale status` still shows the route as advertised — a
   confusing "it worked yesterday" failure mode. Mitigated by testing
   through an actual `sudo reboot` in `implementation.md` step 6, not just
   the initial setup.

## Key Differences

| Aspect | Current | Target |
|--------|---------|--------|
| NAS reachability off-LAN | Not reachable — `ConnectionRefusedError` | Reachable via Tailscale subnet route through the Pi |
| Pi's Tailscale role | Regular tailnet node only | Also a subnet router for `<nas-ip>/32` |
| NAS `pg_hba.conf` | `0.0.0.0/0` (any source) | `<lan-subnet>/24` (Pi's LAN subnet only) |
| `DATABASE_URL` | `<nas-ip>:5433` | Unchanged |

## Rollback Plan
1. On the Pi: `sudo tailscale set --advertise-routes=` (empty value removes
   the advertised route) — or fully `sudo tailscale down && sudo tailscale up`
   without the flag if `set` alone doesn't clear it.
2. In the Tailscale admin console, the route disappears from the Pi's entry
   once no longer advertised — no separate revocation needed.
3. On the NAS: revert `pg_hba.conf`'s line back to `0.0.0.0/0`, restart the
   PostgreSQL package via DSM Package Center.
4. Verify on-LAN access still works (same check as `implementation.md` step
   6's on-LAN regression check) to confirm the rollback didn't itself break
   anything.
