# #13.2: Context

## Issue Description

While prepping `#13` (Pi Deployment + Tailscale) for its first real production deploy, evaluated switching the notification provider from Pushover to a self-hosted `ntfy` server — driven by Pushover's trial ending (would require paying per Apple device) and a preference for self-hosting everything else in this stack (Pi-hole, Postgres, Plex).

That evaluation went deep (see prior conversation) and surfaced a real tradeoff: self-hosted `ntfy` on iOS requires a two-hop delivery mechanism (silent poll-trigger push via `ntfy.sh`'s relay, then the phone fetching real content directly from the self-hosted server) — structurally less reliable than Pushover's single-hop direct alert push, since the second hop rides iOS's more throttleable "background/silent push" category rather than a high-priority "alert" push. For `youn-server`'s stock/price alerts specifically, where a delayed or dropped notification has real cost (missed trading decisions), that reliability tradeoff isn't worth it.

Decision: keep Pushover for `youn-server` (repurchase — the cost is small and justified by reliability). `ntfy`'s self-hosting appeal remains relevant to a separate, unrelated future feature (`claude-keyring`'s notification approve/deny buttons, a different project, lower stakes, more latency-tolerant) — but that's out of scope here, decided independently, whenever that project actually gets built.

What's still being changed: email is dropped as a notification channel regardless of the Pushover/`ntfy` question. `notify_email` already defaults to `False` in `Settings` (effectively unused today) and is no longer wanted going forward — removing the dead code outright rather than leaving it disabled-but-present.

This issue is scoped as `#13.2`, a small prerequisite chore ahead of `#13` — same reasoning as before (better to land this before the first real deploy than after), just much smaller in scope now than originally planned.

## Component / Route Summary

### Current State
`backend/app/services/notifications.py`'s `send_alert()` conditionally calls `send_email()` (gated by `settings.notify_email`, default `False`) alongside `send_pushover()` (gated by `settings.notify_pushover`, default `True`). `_send_email_sync()` handles the actual SMTP send via `smtplib`, using `settings.gmail_user`/`settings.gmail_app_password`.

`backend/app/core/config.py`'s `Settings` has `gmail_user`, `gmail_app_password`, `notify_email` fields.

`.env.example` documents `GMAIL_USER`, `GMAIL_APP_PASSWORD`.

`.doc/architecture.md` describes `notify.py` as "Pushover + SMTP dispatch" (dual-channel).

### Target State
`notifications.py` has no email/SMTP code at all — `send_alert()` only calls `send_pushover()`. `Settings` and `.env.example` drop the `GMAIL_*`/`notify_email` fields. `architecture.md` describes `notify.py` as Pushover-only.

Pushover itself is untouched by this issue — its integration, config fields, and `architecture.md`'s existing "Pushover delivery — the actual pub/sub hop" explanation all remain exactly as they are today.

## Impact & Risk

### Files Changed
- **`backend/app/services/notifications.py`** — remove `_send_email_sync`, `send_email`, the `notify_email` branch in `send_alert()`, and the now-unused `smtplib`/`email.mime.multipart`/`email.mime.text`/`html.escape` imports.
- **`backend/app/core/config.py`** — remove `gmail_user`, `gmail_app_password`, `notify_email`.
- **`.env.example`** — remove `GMAIL_USER`, `GMAIL_APP_PASSWORD`.
- **`.doc/architecture.md`** — drop the SMTP/email half of `notify.py`'s dual-channel description.

### Dependencies
- **`app/consumers/notify.py`**, **`app/services/trading_agents.py`** — both call `send_alert()` only, unaffected (its public signature doesn't change).

### Breaking Changes
None — `notify_email` already defaults to `False`, so no live behavior changes for anyone. Purely dead-code removal.
