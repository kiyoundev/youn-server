# #13.2: Drop Email Notification Channel

## PR / Branch
- **Branch:** `chore/13.2-drop-email-notifications`
- **PR Title:** `main | chore - 13.2 - Drop email notification channel`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [x] No email/SMTP code path remains in `notifications.py`; `smtplib`/`email.mime`/`html.escape` imports removed
- [x] `config.py`/`.env.example` no longer reference `GMAIL_*`/`notify_email`
- [x] `architecture.md` reflects Pushover as the sole notification channel
- [x] Existing Pushover-path behavior in `send_alert()` unaffected — full test suite (272 tests) passes; `test_notify.py` rewritten to drop email-specific tests, Pushover tests untouched/still passing

## Estimated Effort
- Implementation: **0.25h**
- Testing: **negligible** (dead-code removal, no behavior change to the remaining Pushover path)
- **Total: ~0.25h**
