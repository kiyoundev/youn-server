# #13.1: Implementation

## Steps

### 1. Pi — enable IP forwarding (persistent)
- [x] SSH to the Pi over Tailscale: `ssh youn@<pi-tailscale-ip>`
- [x] Check current state: `sysctl net.ipv4.ip_forward` — if it prints `1`, it's already on for this boot, but still verify persistence below (a value of `1` here can be a leftover from a manual `sysctl -w` that won't survive reboot)
- [x] Persist it: create `/etc/sysctl.d/99-tailscale.conf` with `net.ipv4.ip_forward = 1`
- [x] Apply without reboot: `sudo sysctl -p /etc/sysctl.d/99-tailscale.conf`
- [x] Re-check: `sysctl net.ipv4.ip_forward` → `1`

### 2. Pi — advertise the NAS route (persistent)
- [x] `sudo tailscale set --advertise-routes=<nas-ip>/32` (using `set`, not `up`, so this doesn't disturb the Pi's existing Tailscale session/auth state — `set` persists the flag in tailscaled's own state going forward, no systemd unit edits needed)
- [x] Confirm locally: `tailscale status` on the Pi should show the route as advertised (may show as "unapproved" until step 3)

### 3. Tailscale admin console — approve the route
- [x] Open `https://login.tailscale.com/admin/machines` (log in with the account used to set up this tailnet)
- [x] Find `youn-server` (the Pi) in the machine list — it should show a route-pending indicator
- [x] Click it, approve `<nas-ip>/32`
- [ ] Optional: if you don't want to repeat this for future routes on devices you own, look at Tailscale's route "auto approvers" ACL setting — out of scope to configure here, just noting it exists

### 4. Dev Mac — verify "Accept subnet routes"
- [x] Open the Tailscale menu bar app → Preferences (or `tailscale status` from a terminal informational check)
- [x] Ensure the equivalent of "Accept subnet routes" is enabled — on the macOS GUI app this is on by default but worth a visual check since it can be toggled off; if using the CLI-managed tailscaled instead of the GUI app, this is `tailscale up --accept-routes` (only needs setting once, persists)

### 5. NAS — tighten `pg_hba.conf`
- [x] SSH to the NAS (per `#1.5`'s existing admin user/SSH setup)
- [x] Locate `pg_hba.conf` (per `#1.5`, typically under `/volume1/@database/pgsql/` — turned out to be the wrong instance; real one was `/volume1/@appdata/postgresql/data/`, see challenges.md)
- [x] Change the existing line from `host youn_server youn <lan-subnet>/22 md5` (not `0.0.0.0/0` as originally assumed — see `.doc/issues.md`'s correction) to `host youn_server youn <lan-subnet>/24 md5`
- [x] Reload config: `pg_ctl reload` (used instead of a full DSM Package Center restart — sufficient for a `pg_hba.conf`-only change)

### 6. Testing & Validation
- [x] **Off-LAN, Tailscale connected**: from the dev Mac, confirm `<nas-ip>:5433` is reachable — confirmed via `backend/.venv/bin/uvicorn app.main:app --reload` starting cleanly on cellular
- [x] **On-LAN regression check**: confirmed Postgres access still works on-LAN after the `pg_hba.conf` change (same `uvicorn` startup test, still on home Wi-Fi)
- [x] **Reboot survival**: `sudo reboot` the Pi, waited for it to come back, re-ran the off-LAN reachability check without re-running any `tailscale set` or `sysctl` commands — confirmed both the route and IP forwarding persisted

### 7. Cleanup
- [x] Update `.doc/issues.md`: mark `#13.1` done, note the `pg_hba.conf` TODO from `#1.5` as resolved
