# Notifications

## Dispatch

Single entry point in `services/notify.py`:

```python
async def send_alert(title: str, body: str, url: str | None = None):
    await send_pushover(title, body, url)
    await send_email(title, body, url)
```

Both channels run independently — email failure does not block Pushover and vice versa.

---

## Pushover

### Why Pushover

Pushover acts as a proxy to Apple's APNs on your behalf. You send one HTTP POST to Pushover's API — they deliver native push notifications to all your Apple devices simultaneously. No Apple Developer account, no `.p8` key, no Xcode, no per-device token management.

### Requirements

- Free Pushover account at pushover.net → get `User Key`
- Create an Application in Pushover dashboard → get `App Token`
- Install Pushover app on each device:
  - iOS app: $4.99 one-time → covers iPhone + iPad + Apple Watch
  - macOS app: $4.99 one-time → covers Mac
- Store `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` in `.env`

### Device Coverage

| Device | How it receives |
|--------|----------------|
| iPhone | Native push via Pushover iOS app |
| iPad | Native push via Pushover iOS app |
| Mac | Native push via Pushover macOS app |
| Apple Watch | Native push via Pushover watchOS app |

One API call reaches all four devices simultaneously.

### Priority Levels

Most alerts (price drops, `buy_signal`/`take_profit` stock thresholds) send at Pushover's default **Normal** priority. `StockAlert.alert_type = "stop_loss"` threshold crossings send at **High** priority instead — bypasses quiet hours/DND, distinct from every other notification in the system. `take_profit` gets its own distinct wording ("lock in gains") but stays at Normal — hitting a profit target isn't an emergency the way a hard stop is. Not using **Emergency** (repeat-until-acknowledged) for any alert type — that's reserved for "something is actively on fire," overkill for a price threshold actionable within a few minutes either way.

### Implementation

```python
import httpx

async def send_pushover(title: str, body: str, url: str | None = None, priority: int = 0):
    payload = {
        "token":   settings.pushover_api_token,
        "user":    settings.pushover_user_key,
        "title":   title,
        "message": body,
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "View"
    if priority:
        payload["priority"] = priority
    async with httpx.AsyncClient() as client:
        await client.post("https://api.pushover.net/1/messages.json", data=payload)
```

### Free Tier

10,000 messages/month — sufficient for personal alert use indefinitely.

---

## Email (Gmail SMTP)

### Requirements

- Gmail account with 2FA enabled
- Gmail App Password (generated at myaccount.google.com → Security → App Passwords)
- Stored as `GMAIL_APP_PASSWORD` env var

### Implementation

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email(title: str, body: str, url: str | None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = title
    msg["From"] = settings.gmail_user
    msg["To"] = settings.gmail_user  # send to self
    # HTML body with item name, current price, target price, link
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(settings.gmail_user, settings.gmail_app_password)
        smtp.send_message(msg)
```

Limit: 500 emails/day on free Gmail. Well within budget for personal alert use.

---

## Future: Native APNs Swap

If an Apple Developer account is obtained for another project, swapping Pushover for native APNs requires changes to `services/notify.py` only — no architecture changes. The rest of the system (event queue, consumers, scheduler) is unaffected.
