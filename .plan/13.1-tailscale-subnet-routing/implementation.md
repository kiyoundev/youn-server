# #13.1: Implementation

## Steps

### 1. Pi — enable IP forwarding (persistent)
- [ ] SSH to the Pi over Tailscale: `ssh youn@<pi-tailscale-ip>`
- [ ] Check current state: `sysctl net.ipv4.ip_forward` — if it prints `1`,
      it's already on for this boot, but still verify persistence below
      (a value of `1` here can be a leftover from a manual `sysctl -w` that
      won't survive reboot)
- [ ] Persist it: create `/etc/sysctl.d/99-tailscale.conf` with:
  ```
  net.ipv4.ip_forward = 1
  ```
- [ ] Apply without reboot: `sudo sysctl -p /etc/sysctl.d/99-tailscale.conf`
- [ ] Re-check: `sysctl net.ipv4.ip_forward` → `1`

### 2. Pi — advertise the NAS route (persistent)
- [ ] `sudo tailscale set --advertise-routes=<nas-ip>/32`
  (using `set`, not `up`, so this doesn't disturb the Pi's existing
  Tailscale session/auth state — `set` persists the flag in tailscaled's
  own state going forward, no systemd unit edits needed)
- [ ] Confirm locally: `tailscale status` on the Pi should show the route
      as advertised (may show as "unapproved" until step 3)

### 3. Tailscale admin console — approve the route
- [ ] Open `https://login.tailscale.com/admin/machines` (log in with the
      account used to set up this tailnet)
- [ ] Find `youn-server` (the Pi) in the machine list — it should show a
      route-pending indicator
- [ ] Click it, approve `<nas-ip>/32`
- [ ] Optional: if you don't want to repeat this for future routes on
      devices you own, look at Tailscale's route "auto approvers" ACL
      setting — out of scope to configure here, just noting it exists

### 4. Dev Mac — verify "Accept subnet routes"
- [ ] Open the Tailscale menu bar app → Preferences (or `tailscale status`
      from a terminal informational check)
- [ ] Ensure the equivalent of "Accept subnet routes" is enabled — on the
      macOS GUI app this is on by default but worth a visual check since
      it can be toggled off; if using the CLI-managed tailscaled instead
      of the GUI app, this is `tailscale up --accept-routes` (only needs
      setting once, persists)

### 5. NAS — tighten `pg_hba.conf`
- [ ] SSH to the NAS (per `#1.5`'s existing admin user/SSH setup)
- [ ] Locate `pg_hba.conf` (per `#1.5`, typically under
      `/volume1/@database/pgsql/`)
- [ ] Change the existing line:
  ```
  host    youn_server    youn    0.0.0.0/0    md5
  ```
  to:
  ```
  host    youn_server    youn    <lan-subnet>/24    md5
  ```
- [ ] DSM → Package Center → PostgreSQL → Stop → Start (restart to apply)

### 6. Testing & Validation
- [ ] **Off-LAN, Tailscale connected**: from the dev Mac, confirm
      `<nas-ip>:5433` is reachable — reuse the earlier verification
      approach (`asyncpg.connect()` against `DATABASE_URL`, or just start
      the backend: `backend/.venv/bin/uvicorn app.main:app --reload` and
      confirm no `ConnectionRefusedError` on startup)
- [ ] **On-LAN regression check**: connect to the home Wi-Fi directly (or
      ask whoever's home to check) and confirm Postgres access still works
      from the Pi and from a Mac on the LAN — this is the one step that
      could have broken existing access if `<lan-subnet>/24` was mistyped or
      doesn't actually cover the Pi's LAN IP (`<pi-lan-ip>` per `#13`'s
      provisioning note — confirm it falls inside `<lan-subnet>/24`, which it
      does)
- [ ] **Reboot survival**: `sudo reboot` the Pi, wait for it to come back,
      re-run the off-LAN reachability check from step above without
      re-running any `tailscale set` or `sysctl` commands — confirms both
      the route and IP forwarding persisted

### 7. Cleanup
- [ ] Update `.doc/issues.md`: mark `#13.1` done, note the `pg_hba.conf`
      TODO from `#1.5` as resolved
