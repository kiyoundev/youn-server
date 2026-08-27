# Concepts

## API Proxy Pattern (a.k.a. "Backend For Frontend")

Why this section exists: this pattern shows up in nearly every production web app that talks to an API requiring a secret (API key, token, credentials). It's worth understanding once, generally, rather than re-deriving it each time it comes up.

### The problem

A browser is fully inspectable. Anyone using it can open DevTools → Network tab and see every request your page makes — full URL, headers, body. If frontend code called a protected API directly:

```ts
fetch("https://api.example.com/data", {
  headers: { "X-API-Key": "secret-value" },
});
```

`secret-value` is now visible to anyone with access to that browser tab. It can be copied out and reused against the API from anywhere, by anyone. This is true no matter how the key got there — hardcoded, fetched from a config endpoint, injected at build time — if it's in code that runs *in the browser*, it's public.

### The fix: add a hop the browser can't see into

Put a server in between that the browser talks to, which in turn talks to the real API. The secret lives only on that middle server:

```
Browser  →  Your own server (proxy)  →  Protected API
        no secret here            secret attached here,
                                    invisible to the browser
```

The browser only ever sees the first hop. The second hop — server to server — never touches the client, so nothing there is inspectable via DevTools.

### Concrete example from this repo

- **`frontend/src/app/page.tsx`** — browser-side code calls `useSWR("/api/proxy/system/storage", ...)`. This request goes to the *same* Next.js server that served the page. No secret in it.
- **`frontend/src/app/api/proxy/[...path]/route.ts`** — server-side code (never sent to the browser, never visible in DevTools). Receives that request, then makes a *second* request to the real backend, attaching `X-API-Key: process.env.API_KEY` — read from `frontend/.env.local` (dev) or `frontend/.env` (Docker), never from anything the browser can reach.
- **`backend/app/core/auth.py`** — FastAPI's `verify_api_key` dependency checks that header and rejects the request (401) if it doesn't match `backend/app/core/config.py`'s `settings.api_key` (itself loaded from the root `.env`).

Full request path:
```
Browser (no key)
  → GET localhost:3000/api/proxy/system/storage
    → Next.js route.ts (server-side, adds X-API-Key)
      → GET backend:8000/api/system/storage
        → FastAPI verify_api_key checks header → 200 OK with data
    ← JSON relayed back
  ← JSON, browser never saw the key at any point
```

### Why this exact shape (a Next.js "route handler")

Next.js already runs a server to serve your pages — files under `app/api/.../route.ts` just add more server-side endpoints to that same server. No separate proxy service to write, deploy, or keep running. Every major frontend framework has an equivalent (Nuxt server routes, SvelteKit `+server.ts`, Remix loaders/actions) — the feature exists specifically to make this pattern easy.

### Is this actually common?

Yes — this is often called a **BFF (Backend For Frontend)** or just "API proxy route." Any app with a paid/rate-limited/secret-gated API (Stripe, OpenAI, internal services with API keys) that also has a public-facing frontend uses this shape. It's not specific to this project.

### Variations on this pattern

- **"True" BFF — one instance per client type.** Where the term originated (SoundCloud/Netflix): a web app *and* a mobile app *and* a TV app hitting shared backend services each get their **own** BFF, tailored to what that client needs (different data shapes, different aggregation). What this repo has is a simplified single-client BFF — one frontend, so one proxy is enough.
- **API Gateway.** Same secret-hiding property, but as dedicated infrastructure (Kong, AWS API Gateway, Cloudflare) instead of a few lines in your own app server. Adds per-client rate limiting, request/response transformation, many services behind one entry point. Overkill for a single-user app; makes sense with many services or many external consumers.
- **Server-side data fetching — no separate proxy route at all.** Instead of the browser fetching client-side (`useSWR` in `page.tsx`), fetch **during server-side render** (Next.js Server Components, older `getServerSideProps`, Remix loaders). The secret is used server-side while building the HTML; the finished page already has data baked in, so no round-trip proxy endpoint is needed. Tradeoff: no easy client-side polling/revalidation like SWR gives — better fit for data that doesn't need to auto-refresh.
- **Session cookie instead of proxying every call.** Rather than hiding an API key on every request, the backend issues the browser a short-lived, opaque session cookie after login; the browser sends *that* instead of a real secret, and the backend maps the cookie to real credentials server-side. Solves a different problem (user identity/session) than key-hiding, via a similar principle (never expose the real secret to the browser). Not used in this repo — no login/user-account system exists here (see "why did we use BFF over session cookie" note below).
- **Pre-signed URLs — the "don't proxy at all" alternative.** Common for large file transfers (S3, GCS): instead of proxying every byte of a file through your server, the backend generates a short-lived signed URL and hands that to the browser, which talks to the cloud provider directly. Real credentials never leave the backend, but the data itself doesn't route through the proxy either — useful when proxying gigabytes through your own server would be wasteful.

**Why this repo uses the BFF/proxy shape, not session cookies:** a session cookie authenticates a *user identity* ("which logged-in person is this") and needs a login flow, user/session store, expiry handling. This app has none of that — no accounts, no login page, just one person and one static `API_KEY`. The proxy route answers a different question — "is this server-side code allowed to call the backend" — an app-to-app trust check, not a user-identity one. The two aren't mutually exclusive: a multi-user version of this app would likely use both, session cookie for "who's logged in" plus this same BFF proxy underneath still hiding the backend's real key. Session cookies would only earn their keep here if real user accounts get added later.

### Five ways real systems keep secrets out of the browser

The BFF/proxy shape above is one strategy among several industry-standard approaches to the same underlying problem — worth seeing side by side, since which one applies depends on *what* is being protected and *from which threat*, not a single universal answer.

1. **BFF / API proxy** (what this app uses) — secret lives in server-only env, used inside server-only route handlers, per the client/server bundle-splitting mechanism above (`route.ts` never ships to the browser; `API_KEY` never gets baked into client JS since it lacks a `NEXT_PUBLIC_` prefix). The browser gets *output*, never the *code* or the *input* that produced it.
2. **Scoped, "safe-to-expose" keys** (Stripe's `pk_live_...` vs `sk_live_...`) — a fundamentally different strategy: instead of hiding a secret, the third-party service issues a *second, deliberately weak* credential designed to be harmless even if seen. It can tokenize a card, nothing more — it can't charge anyone or read account data. Nothing is technically "hidden" here; the public key is just genuinely safe to show.
3. **Pre-signed URLs / short-lived tokens** (S3, GCS downloads) — server holds the real permanent credentials, and hands the browser a temporary, narrowly-scoped substitute (valid 15 minutes, one file, one operation). If it leaks, it expires soon and can't do much. Same idea as #2 — issue something weaker instead of hiding the real thing — but time-boxed instead of permanently-scoped. Same pattern as "Pre-signed URLs" under Variations above; see there for this repo's specific reasoning on why it doesn't apply here (small JSON payloads, no large-file-transfer cost to avoid).
4. **OAuth PKCE** (mobile apps, SPAs) — the most radical option: no long-lived secret exists at all for this client type. The protocol assumes a shipped app can't keep any secret (it can be decompiled, or its JS can be read), so instead of a fixed client secret, each login generates a one-time, throwaway proof (a code verifier/challenge pair) that's useless after that single exchange completes.
5. **`httpOnly` session cookies** — worth including because it hides from a genuinely *different* threat than everything above. The browser *does* hold this token — but marked `httpOnly`, meaning the page's own JavaScript can't read its value via `document.cookie`. This stops a different attack: malicious JS injected into the page (XSS) stealing the token programmatically. It does **not** hide the cookie from someone opening DevTools' Network tab and looking at outgoing request headers directly — that's a different threat than what `httpOnly` defends against, and it's still fully visible there, on purpose (the browser has to send it automatically on every request to that origin). Related to, but narrower than, "Session cookie instead of proxying every call" under Variations above — that entry covers the *user-identity* question; this one covers specifically the *browser-JS-visibility* half of what a cookie does or doesn't hide.

None of these five is universally "the" right answer — each defends against a specific, named threat (browser DevTools inspection, XSS reading `document.cookie`, network eavesdropping, a leaked-but-scoped credential). This repo only ever needed #1: no third-party-issued scoped key to reach for (it owns the whole API, front to back), no cookies at all so no XSS/`document.cookie` concern, and a real server sits in the loop so there's no mobile/SPA-can't-keep-a-secret scenario forcing PKCE.

## Next.js Dynamic Route Segments — the `[...path]` catch-all convention

Why this belongs here: this bracket syntax is what makes the API Proxy Pattern above possible with a single file instead of one file per backend endpoint — worth understanding the convention itself, not just treating it as boilerplate.

Official docs: [Next.js File-system conventions — Dynamic Routes](https://nextjs.org/docs/app/api-reference/file-conventions/dynamic-routes)

### What the brackets mean

Next.js's App Router derives routes from the folder structure under `app/`. Square brackets mark a folder as a **dynamic segment** instead of a literal path piece:

| Folder name | Matches | `params` shape |
|---|---|---|
| `system/storage/` | only `/system/storage` | none — static route |
| `[id]/` | any single segment, e.g. `/42` | `{ id: "42" }` |
| `[...path]/` | any number of segments, e.g. `/system/storage`, `/analysis/tradingagents/version` | `{ path: ["system", "storage"] }` — an array |
| `[[...path]]/` | same as above, **plus** the base path itself (`/api/proxy` alone) | `{ path: undefined \| string[] }` |

The `...` is what makes it a **catch-all**: without it, `[id]` matches exactly one path segment and nothing deeper. With it, `[...path]` matches *any depth* — one segment, three segments, whatever comes after `/api/proxy/`.

### Why this repo needs it specifically

The proxy pattern (see above) exists to forward *every* backend call through one server-side handler, regardless of which backend endpoint is being called. Without a catch-all, forwarding `/api/system/storage` and `/api/analysis/tradingagents/version` would need two separate hardcoded route files — one per backend path — defeating the point of having a single generic proxy. `[...path]` lets one file, `frontend/src/app/api/proxy/[...path]/route.ts`, catch all of them at once.

### How it flows through the actual code

```ts
// frontend/src/app/api/proxy/[...path]/route.ts
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params        // e.g. ["system", "storage"]
  const url = `${BACKEND_URL}/api/${path.join("/")}...`   // rejoined: "system/storage"
  ...
}
```

A request to `/api/proxy/system/storage` arrives with `path = ["system", "storage"]` — the handler just re-joins the array with `/` and appends it to the backend's base URL. Add a new backend endpoint tomorrow (`/api/analysis/server/version`, say) and it's proxied automatically — no new route file needed, the catch-all already matches it.

### The identifier name is yours to choose — the brackets/ellipsis aren't

`path` (as in `[...path]`) is just a parameter name, becomes `params.path` in code — could equally be `[...slug]`, `[...route]`, `[...segments]`, purely a naming preference. The square brackets and `...` themselves are fixed Next.js syntax; there's no way to get catch-all behavior without them. This repo uses `[...path]`, matching Next.js's own documentation convention for this exact use case.

## Polling vs. pub/sub — data delivery

Core distinction: **who initiates each exchange**.

- **Polling** — the client asks, repeatedly, on a timer: "anything new?" Even if nothing changed since last time. Pull-based.
- **Pub/sub** — the server pushes the moment something happens. The subscriber doesn't ask; it just receives events as they occur. Push-based.

Both exist in this repo, directly comparable:

- **Polling** — `frontend/src/app/page.tsx`'s `useSWR(..., { refreshInterval: 30000 })`. Every 30s, the browser asks the proxy "what's the storage state now?" regardless of whether disk usage actually changed. Simple — any plain HTTP endpoint works, no persistent connection to manage. Cost: wasted requests when nothing changed, plus up to 30s latency before a real change is seen.
- **Pub/sub-like push** — `backend/app/services/stocks.py`'s `FinnhubClient`. One persistent WebSocket, subscribed to tickers; Finnhub pushes a trade event the instant a price tick happens, no repeated asking. Near-zero latency, no wasted requests. Cost: real complexity — a connection that must stay alive, exponential-backoff reconnect (`_listen()`), re-subscribing all tickers on reconnect.

**Terminology nuance:** strict pub/sub (as used for Kafka, Redis pub/sub, MQTT) involves a broker between publishers and subscribers — they never talk directly, only through named topics/channels the broker routes. Finnhub's WebSocket is push-based and event-driven like pub/sub, but it's really a direct server→client push, no broker involved. Same "push, don't pull" property, different architecture underneath — worth not conflating the two.

**The actual broker-mediated pub/sub example already in this repo is Pushover, not Finnhub.** `NotifyConsumer` (`consumers/notify.py`) publishes one message to `https://api.pushover.net/1/messages.json`, keyed by `PUSHOVER_USER_KEY` — a topic identifier, not a device address. Pushover's own servers are the broker: they fan that single publish out to every device currently subscribed under that key (iPhone, iPad, Mac, Apple Watch), and this app never enumerates devices or holds a per-device token. Full delivery diagram: `architecture.md` → "Pushover delivery — the actual pub/sub hop." Textbook pub/sub shape — one publish, N decoupled subscribers, broker owns the fan-out — sitting right next to Finnhub's push-without-a-broker example above. Worth contrasting the two when this terminology comes up again.

**Why storage polls but stocks push, specifically:**

1. **The upstream source itself has no push mechanism.** Finnhub built a WebSocket so clients don't have to poll — that's infrastructure Finnhub provides. Synology's Storage Manager API is pure request/response (log in, ask, get an answer) — no "notify me on change" hook exists. Getting push-style delivery here would mean building your own backend poller anyway, then re-broadcasting over your own WebSocket — doesn't eliminate polling, just moves it one hop earlier and adds a new layer (persistent poller + your own WS server + connection management) on top.
2. **The data doesn't change fast enough to justify that cost even if built.** A stock price can cross an alert threshold in under a second — polling for that either misses the moment or means polling absurdly often. Disk capacity changes over hours/days; being up to 30s stale costs nothing real. Push infra (persistent connections, reconnect/backoff, keeping a connection alive on a resource-limited Pi) is real ongoing cost — not worth it for data this slow-moving.

General rule: match transport to how fast the underlying data actually changes, and whether the upstream source can even emit change events. Push only earns its complexity when both are true.

### Short vs. long polling, and where WebSocket/SSE/webhook fit

The "polling" bucket above actually splits into two, and the "push" bucket above (WebSocket) is one of three distinct push mechanisms — worth separating all five explicitly.

**Short polling** — client asks on a fixed interval; server answers immediately every time (even "nothing changed"). This is what `useSWR(..., { refreshInterval: 30000 })` does above: new HTTP request every 30s, immediate reply.

**Long polling** — client asks; server *holds the request open* without replying until there's something to say (or a timeout hits), then replies and closes. Client immediately re-opens a new request. Feels closer to realtime than short polling (no fixed-interval lag) and wastes fewer empty round-trips, but every single event still costs a full new HTTP request/response cycle — headers, connection setup, the works. A stepping stone between short polling and a truly persistent connection; not used anywhere in this repo.

**WebSocket** — one persistent, full-duplex TCP connection. Either side sends anytime after the initial handshake, no new connection per message. This repo's `FinnhubClient` (`backend/app/services/stocks.py`) uses this — but only in one direction in practice (Finnhub → backend); the backend never needs to push anything back up that same socket, it's just consuming it.

**SSE (Server-Sent Events)** — also a persistent connection, but **one-directional only**: server → client, over plain HTTP (no protocol upgrade, unlike WebSocket). Client can't send data back over the same channel — would need a separate normal request for that. Simpler than WebSocket to set up (browsers auto-reconnect per spec, works over plain HTTP/2). Good fit for exactly the kind of thing Finnhub is being used for here (server has events, client just listens) — WebSocket is arguably more machinery than this repo's actual need (backend never sends anything *up* to Finnhub after subscribing), but WebSocket is what Finnhub's API offers, so that's what's used. Not used natively anywhere in this repo's own frontend↔backend traffic.

**Webhook** — the odd one out: no held-open connection, no client repeatedly asking anything. The event source calls *your* server's URL the moment something happens ("don't call us, we'll call you"). Requires you to expose a publicly reachable endpoint. Server-to-server, not browser-to-server — this is how Stripe/GitHub notify external systems, not how a page updates itself live. Not used in this repo (no inbound integrations that push events at it).

Comparison:

| Method | Connection | Direction | Typical latency | Overhead |
|---|---|---|---|---|
| Short polling | New each request | Client asks, server replies | Up to poll interval | High — many requests, most empty |
| Long polling | Held open, reopened after each reply | Client asks, server replies (delayed) | Low | Medium — still one request per event |
| WebSocket | Persistent | Bidirectional | Very low | Low, after handshake |
| SSE | Persistent | Server → client only | Very low | Low |
| Webhook | None (event triggers an outbound call) | Server → server push | Depends on sender | Low, but needs a public endpoint |

Where this repo's two examples land: SWR/storage tile = short polling. Finnhub client = WebSocket, used push-only in practice (would be SSE-shaped if Finnhub offered SSE instead — the repo's actual data-flow need doesn't require bidirectionality, WebSocket is just the interface Finnhub exposes).

### Layered polling — one loop's output can feed another loop's push (2026-08-03)

Pull and push aren't mutually exclusive alternatives picked once per feature — they can stack, one feeding the other. Worked example from this repo's price-watch flow (`backend/app/scheduler/jobs.py`, `frontend/src/app/watchlist/page.tsx`) — discussed while planning issue #10.1/#10.3, not yet built:

**Outer loop — stays polling, no way around it.** `poll_prices` runs on `interval, hours=6` (`main.py:46-48`), scraping retailer pages. This can never become push — retailers don't offer a "notify me when price changes" API, so *something* has to periodically go ask. Same rule as the Synology/Finnhub comparison above: push only works when the upstream source can emit change events, and here it can't.

**Inner loop — currently polling, could become push.** The browser polls `/api/proxy/items` every 30s (`useSWR(..., { refreshInterval: 30000 })`) regardless of whether the 6h scraper has produced anything new. Unlike the outer loop, this leg *can* become push — server and client are both this app's own code, no third-party API constraint blocking it.

```
Retailer site          Backend scraper         Browser
     │                       │                     │
     │  (no push API)        │                     │
     │<──── poll, 6h ────────┤                     │
     │──── price data ──────>│                     │
     │                       │  writes PriceHistory│
     │                       │  row, emits Event    │
     │                       │                     │
     │                       │<──── poll, 30s ─────┤  (today)
     │                       ├──── JSON reply ─────>│
     │                       │                     │
     │                       │──── SSE push ───────>│  (if adopted)
```

**Correction after reading the actual dispatcher (`backend/app/consumers/dispatcher.py`, `main.py:28,54`):** the existing `Event`/`asyncio.Queue` system is **not** a good host for this. It's one queue, one dispatcher task, and — critically — the queue only ever receives IDs for *alert-worthy* events (price crossed target, stock threshold crossed). Most scrapes never write an `Event` row at all (`jobs.py:142`, the non-alert branch just commits and stops). So a "broadcast on every scrape" push can't be wired in as a fourth consumer of this queue — it structurally never sees the majority of scrapes that would need to trigger it. It has to hook `_process_item` directly, right after the `PriceHistory` insert (`jobs.py:95`), as a sibling to the existing alert-only `Event` write — not a consumer downstream of it.

**What it would take, concretely:**
1. A new broadcast call inside `_process_item`, fired unconditionally on every successful scrape — separate from, and in addition to, the existing conditional `Event`/queue write for alert-worthy crossings.
2. New FastAPI route (`GET /api/events/stream` or similar) holding open SSE connections, fed by that broadcast — likely a lightweight in-memory fan-out (a set of open connections), not DB-backed like `Event`, since a missed "listing changed" push isn't a lost alert — the next poll/reconnect naturally re-syncs.
3. The Next.js proxy (`frontend/src/app/api/proxy/[...path]/route.ts`) currently does one-shot `fetch` → `await res.json()` (GET-only, per the API Proxy Pattern above) — streaming through it needs a different handler shape that relays chunks instead of buffering a single JSON response.
4. Frontend: `EventSource` listening on the proxied stream URL, calling SWR's `mutate(key)` for whatever the event names on receipt — replacing (or supplementing) `refreshInterval` for that resource. Because `status` is computed server-side from `alerted_at` (not stored), this same generic broadcast covers alert-triggered UI updates too — no second event type needed just for that.

The diagram above shows *cadence* (outer 6h poll vs. inner push). The two branches off a single scrape are clearer as a tree — one always fires, one is conditional:

```
Scraper finishes one listing
   │
   ├── always: write PriceHistory + update watch_items (DB)
   │      └── always: broadcast in-memory → SSE → frontend receives push, no polling
   │
   └── only if alert-worthy: write Event row (DB, audit) → asyncio.Queue → dispatcher
          └── → Pushover + email
```

Both branches share a trigger (the same successful-scrape moment inside `_process_item`) but are otherwise independent — different conditions, different transport, different consumer. The alert branch is untouched by this proposal; SSE only adds the always-on branch.

**Status: discussed, not implemented.** Tracked as issue `#36` (merges former `#10.1`, `#10.3` — see `.doc/issues.md`) — real backend surface, its own issue. Extending this same mechanism to stock/portfolio ticks (Finnhub) is a deliberately separate follow-up, `#37`, blocked by `#36` — tick frequency likely needs its own throttling design, not a direct reuse of `#36`'s unconditional-per-scrape broadcast.

### Simple request vs. SSE — the proxy relay mechanics, side by side

Item 3 above ("needs a different handler shape that relays chunks instead of buffering a single JSON response") is easiest to see as a direct comparison — same three participants (Browser, Next.js proxy, FastAPI backend) in both cases, structurally different relay behavior.

```
═══════════════════════════════════════════════════════════════════
A) SIMPLE PROXY REQUEST (existing, e.g. GET /api/proxy/items)
═══════════════════════════════════════════════════════════════════

  Browser                    Next.js Proxy                FastAPI Backend
     │                            │                              │
     │  GET /api/proxy/items      │                              │
     │  (no key — nothing to hide │                              │
     │   on this leg)             │                              │
     ├───────────────────────────>│                              │
     │                            │  GET /api/items              │
     │                            │  X-API-Key: <secret>  ←── key attached
     │                            │  HERE, once, outbound only   │
     │                            ├─────────────────────────────>│
     │                            │                        verify_api_key()
     │                            │                        checks header
     │                            │                              │
     │                            │                        query Postgres
     │                            │                              │
     │                            │  200 OK                      │
     │                            │  {"products": [...]}         │
     │                            │  (no key in response —       │
     │                            │   never echoed back)         │
     │                            │<─────────────────────────────┤
     │  200 OK                    │                              │
     │  {"products": [...]}       │                              │
     │<───────────────────────────┤                              │
     │                            │                              │
     ╵  connection CLOSES — one request, one response, done       ╵


═══════════════════════════════════════════════════════════════════
B) SSE STREAM (proposed, #36 — GET /api/proxy/events/stream)
═══════════════════════════════════════════════════════════════════

  Browser                    Next.js Proxy                FastAPI Backend
     │                            │                              │
  page mounts                    │                              │
  new EventSource(...)           │                              │
     │  GET /api/proxy/          │                              │
     │  events/stream             │                              │
     │  (no key needed)           │                              │
     ├───────────────────────────>│                              │
     │                       route handler starts running        │
     │                            │  GET /api/events/stream       │
     │                            │  X-API-Key: <secret>  ←── key attached
     │                            │  HERE, ONCE, at connection-open│
     │                            ├─────────────────────────────>│
     │                            │                        verify_api_key()
     │                            │                              │
     │                            │                        registers this
     │                            │                        connection in the
     │                            │                        in-memory fan-out
     │                            │                        set (BCAST)
     │                            │  200 OK, streaming...         │
     │  200 OK, streaming...      │<─────────────────────────────┤
     │<───────────────────────────┤                              │
     │                            │      [connection stays open — no          │
     │                            │       Content-Length, never "finishes"]   │
     │         . . . nothing happens for a while . . .            │
     │                            │                              │
     │                            │                         scraper finishes
     │                            │                         one listing:
     │                            │                          ├─ always: write
     │                            │                          │  PriceHistory,
     │                            │                          │  update watch_items
     │                            │                          └─ always: broadcast
     │                            │                             to fan-out set
     │                            │  data: {listing_id:12}\n\n    │
     │  data: {listing_id:12}\n\n │<─────────────────────────────┤
     │<───────────────────────────┤                              │
  onmessage fires                 │                              │
  mutate(historyKey) → SWR        │                              │
  refetches that one listing      │                              │
     │                            │                              │
     │         . . . more time passes . . .                      │
     │                            │                              │
     │                            │  data: {listing_id:19}\n\n    │
     │  data: {listing_id:19}\n\n │<─────────────────────────────┤
     │<───────────────────────────┤                              │
  onmessage fires again           │                              │
     │                            │                              │
     ╵  page navigates away / tab closes                          ╵
     │  connection closes                                         │
     ├── es.close() (useEffect cleanup)                           │
     │                            ├── detects browser disconnect  │
     │                            │   (abort signal), closes its  │
     │                            │   own outbound connection ───>│
     │                            │                          detects disconnect,
     │                            │                          removes self from
     │                            │                          fan-out set
```

| | A) Simple proxy request | B) SSE stream |
|---|---|---|
| Connections opened | 1 per request | 1 per page-mount, held for the page's lifetime |
| Key attached | Once, that one request | Once, at connection-open — never again |
| Data direction | One response, then done | Many events, over time, server-initiated |
| Closes when | Response received (automatic) | Page unmounts (explicit `es.close()`) — must propagate through both hops |
| Browser trigger | `useSWR`, on a 30s timer | `EventSource`, opened once, no timer |
| Browser "loading" state | `isLoading` = fetch Promise unresolved; all three hops' latency collapses into one undifferentiated wait, no partial visibility | N/A in the same sense — data arrives incrementally as events, no single Promise to wait on |

### In-memory fan-out — why a queue, not a callback (2026-08-05)

Came up while walking through #36's `sse.py` design — worth capturing since the reasoning took several passes to land.

**The core problem: two independent async tasks, no direct call path between them.** Inside the FastAPI backend, two loops run concurrently, neither calling the other:

- **Loop A — the scraper** (`_process_item`), runs once every 6h.
- **Loop B — the stream handler**, one instance per open `/api/events/stream` connection, runs for as long as that connection stays open.

Loop A has no way to reach into Loop B and force it to `yield` a chunk to the browser — they're separate coroutines with no shared call stack. They need something both can touch to hand data across. That something is a queue: `broadcast()` (Loop A) calls `mailbox.put(...)`; the stream handler (Loop B) sits on `await mailbox.get()`.

**Concrete trace, one connection, from tab-open to first event:**

| Time | Loop A (scraper) | Queue (the mailbox) | Loop B (this tab's stream handler) |
|---|---|---|---|
| t=0, tab opens | — | created, **empty** | `mailbox = register()` → hits `await mailbox.get()` → **goes to sleep**, zero CPU |
| t=0 to t=6h | not running yet (own 6h timer hasn't fired) | still empty | still asleep |
| t=6h, scheduler fires | scrapes, saves to DB, calls `broadcast({"listing_id": 12})` | `put(...)` → queue now holds **1 item** | — |
| t=6h + instant | goes back to sleep until next cycle | item sitting there | **`put()` wakes Loop B immediately** — that's the entire trick of `await .get()`: paused exactly on "wake me the instant something's put here" |
| t=6h + instant | — | `get()` removes it → **empty again** | resumes with the payload → `yield f"data: {...}\n\n"` → chunk goes out over the open HTTP connection |
| t=6h + instant | — | empty | loops back to `await mailbox.get()` → **asleep again** |
| t=12h, repeat | scrapes again, broadcasts again | item appears again | wakes again |

With N tabs registered, `broadcast()` just repeats the `put()` step once per mailbox — each one independently wakes its own sleeping Loop B.

**Why `Queue` specifically, not a plain variable or `asyncio.Event`:**
- `asyncio.Event` — pure signal, no payload. Loop B would learn "something happened" but not *what* — still need somewhere to stash the actual data.
- **A single shared variable** — could hold the payload, but if two scrapes broadcast before Loop B reads the first, the second `put` silently overwrites it. First event lost, no error, no trace.
- `asyncio.Queue` — bundles both: carries the payload *and*, if two arrive before either is read, keeps both in order rather than overwriting. `.get()` also gives the "sleep until something's there" wakeup for free, same as `Event`.

**Why not a JS-style `on`/`emit` callback instead of a queue:** in Node, a registered callback can call `res.write(chunk)` directly, synchronously, from wherever it's registered — Node's callback model doesn't require "resuming a paused generator," so direct dispatch works fine there. Python's `StreamingResponse` generator can't be driven that way — the ASGI server pulls chunks from Loop B's generator by resuming it, and the *only* thing that can resume a paused coroutine is an awaitable completing (a `Future`, or a `Queue.get()` under the hood). A callback called from Loop A would just run as ordinary function code in Loop A's own context — it has no way to make Loop B's frozen `while True` loop wake up and continue. `await queue.get()` **is** the async-Python equivalent of an event handler here, not an alternative to one. Go's common SSE pattern uses a `channel` per connection for the same underlying reason (goroutines block on channel receives, same shape as `Queue.get()`); Node genuinely doesn't need this mechanism because its I/O model allows direct callback dispatch.

**Generality — this in-memory shape is standard for a single-process app, not a full solution at scale.** This app runs as one Python process, so any open connection lives in that one process's memory, reachable by `broadcast()` directly — an in-memory `set` + `Queue` per connection is genuinely sufficient. Production apps running **multiple server instances behind a load balancer** can't do this — a connection held open by instance #2 is invisible to instance #1's in-memory `_clients`. Those add a real broker in between (Redis pub/sub, NATS); each instance still relays down to its own locally-open connections the same in-memory way, but the broker is what lets *any* instance's `broadcast()` reach connections sitting on *other* instances. Same broker-mediated shape as this repo's existing Pushover example (see "Polling vs. pub/sub" above) — Pushover's servers are the broker for push notifications, Redis/NATS would be the broker for SSE fan-out across multiple backend instances. Not needed here — single Pi, single process — but the reason it'd be needed if this app ever scaled out.

### Multi-tab SSE dedup — three approaches compared (2026-08-05)

Came up while planning #36's frontend `EventSource` wiring: multiple browser tabs of the same page each opening their own SSE connection runs into a real constraint — browsers cap concurrent connections to one origin at **6** under plain HTTP/1.1 (`EventSource` counts against that same budget as every other request to the origin). Confirmed this stack is actually exposed to it — `docker-compose.yml` exposes `backend:8000`/`frontend:3000` directly, no TLS/reverse-proxy in front, so no HTTP/2 multiplexing to sidestep the cap. A 7th open tab silently never gets live updates — no error thrown, the connection just queues behind the cap.

**1. SharedWorker — simplest code, ruled out.** A single JS execution context shared by every same-origin tab (not per-tab, unlike a normal script). First tab creates it, every tab after connects to the same running instance via `MessagePort` — no leader-election logic needed at all, since there's structurally only ever one instance:
```js
self.onconnect = (event) => {
  const port = event.ports[0];
  if (!es) { es = new EventSource(url); es.onmessage = (e) => ports.forEach(p => p.postMessage(e.data)); }
  port.start();
};
```
Ruled out specifically because **iOS Safari has never supported `SharedWorker`** — desktop Safari added it in v16 (2022), iOS never has, no fallback exists (`new SharedWorker(...)` just throws). Since all iOS browsers are forced onto WebKit, this breaks on every iPhone/iPad browser, not just Safari proper.

**2. BroadcastChannel + Web Locks leader election — chosen.** Every tab calls `navigator.locks.request("sse-leader", callback)`; the browser's lock queue guarantees exactly one holder at a time and — the key property — **auto-releases the lock if the holding tab closes or crashes**, no cooperation from that tab required. The callback holds the lock forever by awaiting a promise that never resolves:
```js
navigator.locks.request("sse-leader", async () => {
  becomeLeader();               // opens the real EventSource, relays via BroadcastChannel
  await new Promise(() => {});  // never resolves — released automatically on tab death
});
```
Whichever tab acquires the lock opens the real `EventSource` and relays every message out via `new BroadcastChannel(...)` for other tabs to consume; followers just listen on the channel, no `EventSource` of their own. When the leader tab closes, its lock auto-releases and the next queued tab's callback fires — instant promotion, no heartbeat/staleness-timeout logic needed (this is what makes it simpler than a hand-rolled `localStorage`-based election). Broadly supported, including iOS Safari 15.4+ — the deciding factor over SharedWorker. Full implementation: `.plan/36-wishlist-page-real-data-sse/implementation.md` §6, decision record: `challenges.md` #7.

**3. Infra-level fix (HTTP/2 in front) — considered, out of scope.** The connection cap is HTTP/1.1-specific; HTTP/2 multiplexes many streams over one TCP connection, so the cap disappears regardless of tab count. Catch: browsers only negotiate HTTP/2 over TLS, and this stack has no TLS termination today. Cheapest path given this network already runs Tailscale: `tailscale serve https / http://localhost:3000` on the Pi auto-provisions a real cert for the tailnet's `.ts.net` domain and terminates HTTP/2, no new docker service, no manual cert handling — only fixes it for traffic routed through Tailscale, not plain LAN IP access. Set aside as an infra decision independent of this feature, not because it doesn't work.

**Why not just "accept it" outright:** initially the leading option given low realistic tab count for a personal app — set aside once leader election turned out to be ~30-40 lines total (election + relay), cheap enough that solving it properly cost barely more than documenting the limitation would have.

## Related but distinct concepts (don't confuse these)

- **Reverse proxy** (nginx, Cloudflare) — sits in front of a server for routing/TLS/caching, usually doesn't add app-specific secrets to requests. Infrastructure-level, not app-code-level.
- **API gateway** — a reverse proxy with more app-aware features (rate limiting per client, auth, request transformation) — same secret-hiding property as a BFF route, larger in scope, usually its own dedicated service rather than a few lines in your existing frontend server.
- **CORS** — a separate, unrelated browser security mechanism (controls which *origins* can call an API from a browser at all). Doesn't hide secrets; a misconfigured CORS policy doesn't fix the "key visible in DevTools" problem, and a correct one doesn't create it either.

## Common mistake to avoid

In Next.js specifically: any env var prefixed `NEXT_PUBLIC_` gets bundled into browser-shipped JavaScript **on purpose** — that prefix exists for values that are fine to expose (e.g., a public analytics ID). Never prefix a secret with `NEXT_PUBLIC_`. `API_KEY` (no prefix) in `frontend/.env.local` stays server-only precisely because it lacks that prefix — that's the mechanism, not a convention you can skip.

## Six production API practices — what's actually here vs. what's a real gap

A commonly cited checklist of what separates "works in a demo" from "survives production traffic." Going through all six against this repo's actual API:

- **Rate limiting** — reject excessive requests to protect the backend. **✅ Present.** `POST /api/poll/prices`/`stocks` limited to 1 call per 5 minutes (in-memory timestamp, `Issue #8`).
- **Authentication** — verify caller identity. **✅ Present, simpler tier.** `X-API-Key` header + `verify_api_key` dependency (`core/auth.py`) — a single static shared secret, not per-caller. The more sophisticated version of this is a cryptographically signed token (JWT): carries a signed, verifiable claim (identity + expiry) checkable without a DB lookup, and supports distinguishing *which* caller this is and revoking one without rotating a key everyone shares. Static shared-key auth is the right tradeoff here because there's only one real caller (you, via your own frontend) — JWTs earn their complexity once there are multiple distinct clients/users needing separate identities.
- **Versioning** (e.g. `/v1/api/...`, so old clients don't break when the API changes) — **❌ Not present, reasonably so.** Frontend and backend deploy together, same repo, same release — there's no "old client still calling a stale API shape" scenario to protect against. Matters once a third party depends on this API independent of your own deploy cadence.
- **Idempotency** (retrying a failed request, e.g. after a dropped connection, shouldn't create duplicate side effects — usually an idempotency-key header the server caches results against) — **❌ Real gap.** `POST /api/items`/`stocks` would create a duplicate row if a client retried after a network blip mid-request. Low practical risk today (single client, retries are rare and you'd notice), but a genuine hole if this ever gets a flakier or automated caller.
- **Pagination** (return large lists in bounded batches instead of all-at-once) — **❌ Not present.** `GET /api/items`/`stocks` return full lists, unpaginated. Fine at dozens-of-rows scale; would need addressing if either list grew into the thousands.
- **Caching** (skip re-fetching/re-computing unchanged data) — **Partial.** SWR gives client-side cache/dedup already (polling section above). No server-side response caching exists — `GET /api/system/storage` re-logs into DSM and re-queries on every single call, even if called twice in the same second. Worth revisiting once faster-polling tiles (CPU%, e.g. every 2-5s) exist, since repeatedly re-reading unchanged local data on every tick is pure waste even though it's cheap per-call.

Overall: 2 of 6 solid, the other 4 are real gaps — but ones that specifically don't bite *yet* because this is a single-user app where you control every client that talks to it. Worth revisiting this checklist if the app ever grows past "just me."

## Locks (Mutexes) — coordinating concurrent code that shouldn't overlap

Why this section exists: both examples below reach for `asyncio.Lock` to fix a real bug, but neither explains the underlying concept on its own terms. Worth understanding once, generally — this is a decades-old computer science primitive, not something specific to Python, `asyncio`, or this repo.

### The problem: two things racing to do something exactly once

Async code frequently has many logical tasks running "at the same time" (interleaved on one event loop, or genuinely parallel across processes/machines in other languages). Without coordination, two of those tasks can both check a condition, both see it as unmet, and both act on it — even though only one of them should have.

Concretely, the shape that recurs: `if not already_done: do_the_thing()`. Read in isolation this looks safe. Under concurrency it isn't — between the check and the action, another task can run the exact same check, see the same "not done yet" answer, and start doing the same thing too.

### The fix: a lock (mutex — "mutual exclusion")

A lock is a single shared token that only one piece of code can hold at a time. Everyone else who wants it has to wait until the holder releases it.

The classic mental model: a single bathroom key on a hook. Person A takes the key, goes in. Person B tries to take it, finds the hook empty, and just waits there. A finishes, hangs the key back up. B, waiting, takes it immediately. Nobody's ever inside at the same time — even though both wanted in simultaneously.

In Python's `asyncio`:
```python
lock = asyncio.Lock()

async def do_the_thing():
    async with lock:   # wait for the key; auto-releases even if an exception happens inside
        ...             # only one caller's body runs at a time here
```
`asyncio.Lock` is standard library, not project-specific — `threading.Lock` is the equivalent for OS threads, and essentially every language with concurrency has some form of this (`Mutex` in Rust, `sync.Mutex` in Go, `synchronized` in Java). Same concept, different syntax.

### The pattern both examples below use: double-checked locking

Naively wrapping the *entire* check-and-act sequence in a lock works, but forces every caller to wait for the lock even in the overwhelmingly common case where nothing needs doing (the thing's already set up). Double-checked locking adds a fast, lock-free check first, and only pays the lock's cost on the rare occasion it's actually needed:

```python
async def ensure_ready():
    if already_set_up():          # fast path — no lock, correct once things are steady-state
        return
    async with lock:               # slow path — only reached when it might not be set up yet
        if already_set_up():      # re-check — someone else may have finished while we waited
            return
        do_the_setup()
```
The **second** check is what actually prevents duplicate work — it catches the case where another caller raced ahead and finished while this one was waiting for the lock.

### Two concrete instances of this exact pattern in this repo

| | `SynologyClient._get_sid` | `PatchrightScraper.start_browser` |
|---|---|---|
| What's being protected | DSM's session slot — a *second* login silently invalidates the *first*'s session ID | The browser process itself — launching twice wastes memory/CPU and could corrupt the shared profile directory |
| The race, unguarded | Two concurrent DSM calls each log in independently → whichever finishes last wins, the other holds a now-dead session ID → `503`, code 119 (see "Concurrent Session Invalidation" below, and the DSM 503 write-up under Challenges) | Multiple concurrent scrapes (e.g. a bulk-add of several `amazon.ca` listings) each see no browser running yet → each launches its own Chromium instance |
| Status | Fixed — implemented, live | Planned — `#40`, not yet built |

Both are the *same* underlying shape: "expensive setup step, must happen at most once, multiple concurrent callers might all trigger it simultaneously." The lock doesn't make the setup step itself faster — it makes "only one caller actually does it" true regardless of how many ask at once.

### Related but distinct: Lock vs. Semaphore vs. Queue vs. Event

Easy to conflate since they're all `asyncio` concurrency primitives — each solves a different problem:

- **`Lock`** (this section) — at most **one** caller in the guarded section at a time. Binary: held or free.
- **`Semaphore(n)`** — at most **n** callers at a time, `n > 1`. Already used in this repo: `items.py`'s `_PROBE_CONCURRENCY` bounds concurrent routing-probes during bulk-add (`#10.2`); the same pattern is planned for `#41`'s concurrent background scrapes. A `Lock` is really just `Semaphore(1)` conceptually, but Python exposes them as separate types since a binary lock has simpler, stricter semantics (e.g., only the holder should release it).
- **`Queue`** — hands *data* from one task to another, with built-in ordering and backpressure. See "In-memory fan-out — why a queue, not a callback" above for this repo's SSE broadcast use.
- **`Event`** — a one-shot or reusable "something happened" signal, no payload. Mentioned above as what `Queue` was chosen *over* for the SSE case, precisely because it lacks a payload.

None of these substitute for each other — picking the wrong one is a common source of subtle concurrency bugs (e.g., using a `Lock` where a `Semaphore` was needed silently serializes work that was safe to run in parallel; using a plain variable where a `Queue` was needed silently drops data, as covered above).

## Concurrent Session Invalidation — a "successful login" isn't a guarantee

**The generalizable lesson:** a `success: true` response from a login call only means the session was valid *at that instant*. It's not a durable guarantee — anything else sharing that same identity slot (your own app's next request, a concurrent call, even a browser tab open to the same account) can invalidate it a moment later. Code that assumes "I just logged in successfully, so my session is safe to use for the next step" is implicitly assuming exclusive access to that identity — true only if something in your own code actually enforces it. Not Synology-specific: any API with single-active-session auth, seat-limited licensing, or similar exclusivity models has the same trap.

**Solution space — four ways to prevent the collision:**

| Approach | What it does | Fixes the race? | Cost / tradeoff |
|---|---|---|---|
| **A. Lock — serialize the whole cycle** | `asyncio.Lock()` around the login→fetch→logout body — only one cycle runs at a time | Yes, completely | Overlapping calls wait (sub-second) instead of running in parallel; doesn't reduce total calls made |
| **B. Server-side cache** | Cache the result for N seconds; repeat calls within the window skip the external call entirely | Reduces odds, doesn't guarantee | Two cache-miss calls right at TTL expiry can still race — complements the lock, doesn't replace it |
| **C. Reuse one persistent session** | Log in once, hold the session, reuse across calls; only re-login on failure | Yes, by removing the cause (frequent re-logins) rather than guarding the symptom | More moving parts: detect a dead session, re-login transparently, decide session lifecycle |
| **D. Unique session identity per request** | Login with a fresh session identifier each time so calls don't share a slot | Sidesteps it | Works against the platform's session model rather than with it; sessions can leak if cleanup doesn't fire (crash/timeout); the platform may cap total concurrent sessions per account |

**Chosen (refined): C (reuse one persistent session), with A's lock narrowed to guard only the refresh step, plus reactive retry-on-invalid-session.** Initial plan was A alone (lock around the whole login→fetch→logout cycle) — correct, but it doesn't address *why* logins were happening so often in the first place (a fresh login on every single poll). The better-practice version, matching how real SaaS SDKs (Stripe, `boto3`, Google Cloud clients) handle session-based auth: cache the session identifier once, reuse it across calls, and only re-authenticate reactively when a call actually comes back "invalid session" — since DSM's API never advertises a session's expiry up front, there's nothing to proactively schedule a refresh against. The lock's job shrinks accordingly: it no longer wraps every request, only the rare refresh moment, so normal calls with a still-valid cached session never wait on anything (a single-flight pattern — if several requests discover an expired session at once, only one of them actually re-logs in; the rest wait for that same refresh and reuse its result).

```python
class SynologyClient:
    def __init__(self) -> None:
        self._sid: str | None = None
        self._lock = asyncio.Lock()

    async def get_storage(self) -> StorageState | None:
        if not self._enabled:
            return None
        async with httpx.AsyncClient(timeout=10, verify=settings.synology_verify_ssl) as client:
            sid = await self._get_sid(client)
            if not sid:
                return None
            state = await self._fetch_storage(client, sid)
            if state is None:  # specifically an invalid-session response — refresh once and retry
                sid = await self._get_sid(client, force_refresh=True)
                if not sid:
                    return None
                state = await self._fetch_storage(client, sid)
            return state

    async def _get_sid(self, client, force_refresh: bool = False) -> str | None:
        async with self._lock:
            if self._sid and not force_refresh:
                return self._sid
            self._sid = await self._login(client)
            return self._sid
```

Precision needed for the retry condition: `_fetch_storage` currently collapses *every* kind of failure (network error, DSM offline, malformed response, invalid session) into a bare `None`. Retrying-with-relogin should trigger only for a genuine invalid-session response (DSM error code 119 or 106) — otherwise a scenario like "DSM is actually offline" gets a pointless extra login attempt tacked on before failing anyway. Needs `_fetch_storage` to surface *which* kind of failure occurred, not just success/failure.

B (server-side response cache) was considered separately and set aside — it solves a different problem (reducing total DSM traffic) at the cost of showing stale data until the TTL expires, which isn't worth it for a bug-fix; caching remains a real, independent gap (see "Six production API practices" above) worth revisiting later on its own merits. D (unique session name per request) stays ruled out — fights the platform's session model instead of working with it.

**What this changes about the request pattern — fewer logins, not just safer ones:**

Current behavior — every single poll is a full three-call DSM round-trip:
```
Poll #1 (t=0s):  Backend → DSM: login → sid_1 → fetch (sid_1) → logout
Poll #2 (t=30s): Backend → DSM: login → sid_2 → fetch (sid_2) → logout
Poll #3 (t=60s): Backend → DSM: login → sid_3 → fetch (sid_3) → logout
```
More logins happening more often is directly what created more chances for two to collide — this is the actual root cause underneath the race, not just a symptom of missing a lock.

Proposed cached-session behavior — login only happens when actually needed:
```
Poll #1 (t=0s):  Backend → DSM: login (no cached sid yet) → sid saved in memory
                          → DSM: fetch (uses saved sid) → success

Poll #2 (t=30s): Backend → DSM: fetch (reuses the SAME sid from poll #1, no login) → success

Poll #3 (t=60s): Backend → DSM: fetch (still reusing the same sid) → "invalid session" ❌
                          → Backend notices it's specifically an invalid-session error
                          → DSM: login again → new sid saved
                          → DSM: fetch (retry, with fresh sid) → success
```
Most polls become a single DSM call instead of three — fewer sessions created means fewer opportunities for two to overlap in the first place, on top of the narrow lock making any remaining overlap safe.

## Claude API statelessness — authentication ≠ conversation memory (2026-07-26)

Came up while designing a planned chatbot feature (discuss a TradingAgents stock report across multiple turns). Two separate axes got briefly conflated while planning it, worth keeping permanently distinct.

**Axis 1 — how you authenticate.** API key (`x-api-key` header) vs. OAuth login tied to a Claude.ai account/subscription (`Authorization: Bearer <token>` + `anthropic-beta: oauth-2025-04-20` header, obtained via `ant auth login`). This changes *who pays and how* — metered per-token API billing vs. a subscription's bundled usage — nothing else.

**Axis 2 — whether the API remembers your conversation.** A property of the `/v1/messages` endpoint itself, completely independent of axis 1. The Messages API is **stateless**: no `session_id`, no server-side memory, full `messages` history required on every single request. This is true regardless of which credential type hits the endpoint — same request/response shape either way.

**The mixup:** after agreeing to use OAuth/subscription auth instead of a metered API key, it was easy to assume that also meant the API would handle conversation persistence automatically (something like Claude Code's `/resume`). It doesn't — `/resume` is a Claude Code *product* feature, not an API feature. Claude Code stores your session transcripts locally on your own machine and resends the full history itself, exactly like any other caller would have to.

**The clean proof these two axes don't interact:** Claude Code itself authenticates via OAuth/subscription login (the exact mechanism being adopted here) and *still* keeps its own local session files for `/resume` to work. If OAuth auth granted server-side conversation memory, Claude Code wouldn't need local session storage at all — it could just say "resume session X" and let the server remember. It can't, so it doesn't. Same evidence applies to any app built on the plain Messages API: switching auth mechanisms never removes the need to persist and resend history yourself.

**What this means concretely for the planned chatbot feature:**
- A new `ChatMessage` table (`analysis_result_id` FK, `role`, `content`, `created_at`) is the only way "continuing a conversation" works — no shortcut, no server-side session to lean on.
- Every turn: load all prior `ChatMessage` rows for that analysis → build the full `messages` array → append the new user turn → send the *whole* array to Claude → persist both the user message and Claude's reply as new rows.
- The stock report itself (loaded from `AnalysisResult.report_path`) is stable across every turn in one chat thread — belongs in a cached `system` block (`cache_control: {type: "ephemeral"}`), not resent as part of the growing `messages` history, so repeat turns don't re-pay full input cost for the same report text.
- A genuinely different product surface — Managed Agents — *does* offer real server-side session persistence (`sessions.create()` + `sessions.events.list()`), but that's a heavier hosted-sandbox-per-session model built for open-ended agentic work, not a fit for "answer questions about one report."

## Hoisting — one word, two unrelated concepts (2026-07-28)

Came up during a code review of `frontend/src/app/watchlist/page.tsx`. Worth keeping permanently distinct — they share a name, not a mechanism, and conflating them is a common source of confusion.

**1. JavaScript hoisting (the language-spec meaning).** Something the JS engine does automatically, before code runs — not a technique anyone applies on purpose. `var` and `function` declarations are processed before execution starts, as if moved to the top of their scope:

```js
console.log(x); // undefined — not a crash
var x = 5;
```

`let`/`const` are also hoisted, but land in the "temporal dead zone" (TDZ) — the binding exists, but touching it before its declaration line throws:

```js
console.log(y); // ReferenceError: Cannot access 'y' before initialization
let y = 5;
```

Function *declarations* hoist their entire body (callable before they appear in the file):

```js
foo(); // works, logs "hi"
function foo() { console.log("hi"); }
```

But a function *expression* assigned to `const` doesn't get that treatment — it follows the `const` TDZ rule above:

```js
bar(); // ReferenceError
const bar = () => console.log("hi");
```

None of this is written on purpose — it's a parser rule, useful mainly for understanding *why* certain reference-before-declaration bugs happen.

**2. "Hoisting" as a refactoring word (the everyday code-review meaning).** A human deliberately moving a piece of code from an inner scope to an outer one, by hand, as a refactor. Borrows the word because the *direction* looks similar (code moves upward to a scope that runs less often) — but the *mechanism* is nothing like #1: no engine involved, no TDZ, no parse-time behavior. Just: "this doesn't need to be re-created every time this function runs, so move it somewhere that only runs once."

Concrete example from this repo: `emptyNewItem` in `watchlist/page.tsx` was originally declared *inside* `WatchlistPage()`:

```tsx
export default function WatchlistPage() {
  const emptyNewItem = { name: "", targetPrice: "", urls: "" }; // rebuilt every render
  const [newItem, setNewItem] = useState(emptyNewItem);
  ...
```

`useState(x)` only reads `x` on the component's first render — every render after that, React ignores whatever gets passed in. So the object literal was being allocated fresh on every render for no benefit; `useState` was already throwing away all but the first one. Not a live bug (nothing consumed the object's identity), but a landmine: if a later edit put it in a `useEffect` dependency array, that effect would fire every render forever, since dependency arrays compare by reference and a freshly-allocated object is never `===` to the previous render's object, even with identical contents.

Fix — hoist it to module scope, alongside the file's other true constants (`STATUS_BADGE`, `formatLastChecked`):

```tsx
const emptyNewItem = { name: "", targetPrice: "", urls: "" }; // created once, ever

export default function WatchlistPage() {
  const [newItem, setNewItem] = useState(emptyNewItem);
  ...
```

Same pattern applies to hoisting a function definition out of a component so it isn't redefined every render, or hoisting a regex literal out of a hot loop so it's compiled once instead of once per iteration.

**The one-line way to keep them apart:** #1 is a rule the JS engine follows automatically when parsing code. #2 is an instruction a human carries out by hand, usually in response to a reviewer saying "hoist this." Same English word, unrelated mechanism underneath — in a React/JS codebase, "hoist this" in review means #2 essentially every time.

## asyncio concurrency — event loop, coroutines vs Tasks, and why it isn't parallelism (2026-08-15)

Came up while planning `#41`'s background first-scrape (step 1: extracting `spawn()` to `app/core/background_tasks.py`). Worth a permanent write-up — the concurrency-vs-parallelism distinction and the no-preemption rule both bite in non-obvious ways once real concurrent scrapes start running (`#41`'s `Semaphore(3)`, step 3, not yet built).

### Concurrency vs parallelism — not the same thing

- **Concurrency** — dealing with multiple things over an overlapping time period, by interleaving. Never two things running at the literal same instant; just switching between them whenever one goes idle.
- **Parallelism** — actually doing multiple things at the literal same instant. Requires multiple physical execution units (CPU cores, separate machines).

`asyncio` gives concurrency, not parallelism. One thread, one interpreter, one event loop. At any given nanosecond at most one coroutine's bytecode is executing — what makes it *feel* faster than doing things one-after-another is that most of the wait isn't CPU work at all (network round-trip, disk I/O, a timer) — the loop fills those idle gaps with other coroutines' work instead of just blocking on one thing at a time.

This only helps **I/O-bound** work. CPU-bound work has no idle gaps to fill — see the interruption case below.

### Coroutine vs Task, traced literally

```python
async def make_coffee():
    print("start coffee")
    await asyncio.sleep(3)
    print("coffee done")

async def make_toast():
    print("start toast")
    await asyncio.sleep(2)
    print("toast done")
```

Calling `make_coffee()` does nothing yet — it returns a coroutine object, inert until something drives it. `await` and `create_task` drive it in structurally different ways:

**Sequential — `await` inline:**
```python
async def main():
    await make_coffee()   # blocks here until fully done
    await make_toast()
```
Trace: `main` pauses at `await make_coffee()`, hands control to `make_coffee`'s body, which itself pauses at `sleep(3)`. Nothing else is scheduled, so the loop just waits out the 3s, resumes `make_coffee`, it returns, *only then* does `main` even start `make_toast()`. **Total: 5s.** Nothing ran concurrently — `await` always means "block me here until this finishes."

**Concurrent — `create_task` first, `await` after:**
```python
async def main():
    coffee_task = asyncio.create_task(make_coffee())  # scheduled immediately, doesn't wait
    toast_task = asyncio.create_task(make_toast())
    await coffee_task
    await toast_task
```
`create_task()` is instant bookkeeping — registers the coroutine with the loop's ready-queue and returns a `Task` handle right away, no waiting. Both tasks are now independently schedulable *before* either is awaited. Loop runs `make_coffee`'s body to its `sleep(3)`, parks it, runs `make_toast`'s body to its `sleep(2)`, parks it too — now watching two timers. Toast's fires at t=2, coffee's at t=3. **Total: 3s** — the longer of the two, not the sum. This is the entire value `create_task`/`spawn()` adds over a plain `await`.

### The CPU-intensive case — no preemption, ever

What happens if coffee's timer fires while toast is mid-execution, not paused at an `await`?

```python
async def make_toast():
    print("start toast")
    await asyncio.sleep(2)
    do_expensive_cpu_work()   # 5 real seconds, no await inside
    print("toast done")
```

```
t=0   both tasks parked, coffee timer @3, toast timer @2
t=2   toast_task resumes, enters do_expensive_cpu_work()
t=3   coffee's timer fires — coffee_task becomes "ready" — but the loop is
      still stuck inside do_expensive_cpu_work(), which has no await, so
      it can't check anything else
t=7   do_expensive_cpu_work() finally returns, toast_task finishes
t=7   ONLY NOW does the loop check its ready-queue, sees coffee_task has
      been ready since t=3, resumes it
```

Coffee's wakeup was delayed 4s past when it was actually ready — not a bug, just the rule: **a coroutine can only be paused at a point it names itself, via `await`. The loop cannot interrupt running code mid-execution — no preemption exists in asyncio.** A coroutine that runs a long stretch with no `await` inside blocks *everything* else in the process for that stretch, not just itself.

Direct relevance to `#41`: if anything in the scrape path (`process_item`, Patchright driving) does synchronous blocking work — a non-async DB call, `time.sleep()` instead of `asyncio.sleep()`, a sync HTTP call — it freezes the *entire* event loop for that duration, stalling unrelated FastAPI request handlers too, not just the other concurrent scrapes. This is why the issue's acceptance criteria explicitly call for verifying concurrent heavy-scrape behavior live rather than assuming it from `#10.2`'s lighter probe precedent — a hidden blocking call would only surface under genuine concurrent load.

### Is Python always single-threaded? Three distinct mechanisms

| Mechanism | Real OS threads/processes? | Parallelism? | Notes |
|---|---|---|---|
| `threading` | Yes, real OS threads | No — GIL means only one thread executes Python bytecode at a time, ever | Still helps I/O-bound work (a thread blocked on `socket.recv()` releases the GIL while blocked) |
| `multiprocessing` | Yes, separate OS processes, separate interpreters/GILs | **Yes** — actual multi-core use | Higher overhead — no shared memory by default, data must be serialized between processes |
| `asyncio` | No — one thread, one loop | No | Not just GIL-single-threaded like `threading` — no OS thread-switching involved at all; a coroutine only yields control at an `await` it names itself |

So Python *can* do real parallelism (`multiprocessing`), just not via `asyncio` or `threading` for CPU-bound work. `asyncio`'s single-threadedness applies specifically to the coroutine code itself — Patchright's actual browser is presumably its own OS process, and DB drivers may use thread pools under the hood for blocking calls; asyncio's cooperative loop is just the layer coordinating *this app's* Python-level coroutines.

### Worked example from this repo: `spawn()` and why it isn't `async def`

`backend/app/core/background_tasks.py` (extracted from `trading_agents.py` in `#41` step 1, now shared with the item/listing background-scrape use case):

```python
_background_tasks: set[asyncio.Task[None]] = set()

def spawn(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
```

**The GC problem this solves.** `asyncio.create_task(coro)` alone is a footgun: the loop does not hold a strong reference to the returned `Task` for you. If nothing else does either, the `Task` object's refcount hits zero the moment its creator's stack frame tears down, and CPython is free to garbage-collect it — mid-execution, silently, no exception, no log. For `#41` specifically: `create_item`/`create_listing` `spawn()` a background scrape per listing, then immediately `return` their HTTP response. Without a held reference, the response going out tears down the request handler's frame, and the just-scheduled scrape `Task` could be collected before Patchright's `page.goto()` even resolves — a listing stuck in "Processing" forever, no error anywhere pointing at why.

`_background_tasks` fixes it: a module-level set, living as long as the process, holds a strong reference from the moment `spawn()` runs until `add_done_callback` removes it — which only fires once the task has actually finished (success, exception, or cancellation), so the registry self-cleans without ever dropping a reference early.

**Why `spawn()` itself is plain `def`, not `async def`.** `async def` only buys two things: calling it returns a coroutine object instead of running immediately, and it's the only kind of function allowed to contain `await`. `spawn()` needs neither — every line inside it (`create_task`, `set.add`, `add_done_callback`) is instant, synchronous, in-memory bookkeeping; nothing in it ever needs to pause and wait for something external. The only real constraint is that `asyncio.create_task()` needs a *running* event loop to register with — so `spawn()` must be *called* from somewhere already executing inside the loop (an `async def` function mid-execution, like `create_item`), even though `spawn()` itself doesn't need to be one. Rule of thumb generally: mark a function `async def` only when its own body needs to `await` something — a function that's purely instant bookkeeping about async machinery stays a plain `def`.

### Real subprocess parallelism vs one shared browser — TradingAgents vs the scraper

Both features use `spawn()`, but their concurrency underneath is architecturally opposite — worth contrasting precisely rather than assuming they work the same way.

**TradingAgents (`run_analysis`, `backend/app/services/trading_agents.py`) — a new OS process per ticker.**
```python
process = await asyncio.create_subprocess_exec(
    settings.tradingagents_venv_python,
    _WRAPPER_SCRIPT,
    alert.ticker,
    ...
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout_task = asyncio.create_task(_drain_stdout(process))
stderr_task = asyncio.create_task(_watch_stderr(process, result_id, idle_timeout))
```
Every analysis launches a brand-new, independent Python interpreter subprocess — real OS-level parallelism, two tickers' subprocesses can run on two different CPU cores at the literal same instant, entirely outside asyncio's cooperative model. asyncio's job here isn't to make the heavy work (LLM calls, agent debate rounds) concurrent — that's already parallel via the OS. Its job is just to *watch* the subprocess without blocking anything else: `await process.stderr.readline()` pauses on pipe I/O (waiting for the child to write something), letting the loop interleave between however many tickers' watcher-`Task`s are live. Two `Task`s per subprocess (`stdout_task` + `stderr_task`, drained concurrently rather than sequentially) also avoids a classic subprocess deadlock — reading one pipe fully before touching the other risks the child blocking on a full stderr buffer while you're still stuck draining stdout.

**Scraper (`PatchrightScraper`, `backend/app/services/scraper/patchright_scraper.py`) — one shared browser, launched once.**
```python
class PatchrightScraper(BaseScraper):
    _context: BrowserContext | None = None   # class-level — one instance, whole app lifetime

    @classmethod
    async def start_browser(cls) -> None:
        if cls._context is not None:
            return                            # already running — no-op
        async with cls._start_lock:            # double-checked locking, see Locks section above
            if cls._context is not None:
                return
            cls._context = await cls._playwright.chromium.launch_persistent_context(...)
```
`_context` is a class attribute — one Chromium process, shared by every scrape, for the app's whole uptime (until `recycle_browser()` cycles it). `start_browser()`'s lazy launch + `_start_lock` is the double-checked-locking pattern from the Locks section above, applied to a browser launch instead of a DSM login. Every scrape after the first just sees `_context is not None` and skips straight past — **no new OS process per scrape.** Concurrent scrapes instead each call `_context.new_page()` — a new **tab** inside the one already-running browser, not a new process.

The actual `await` boundary is `page.goto(url)`, `page.content()`, `.text_content()` — these aren't running JS inline in the Python process. Patchright talks to the real Chromium process over the **Chrome DevTools Protocol (CDP)**, a message-passing protocol over a pipe/websocket. `await page.goto(url)` sends a CDP command and pauses until Chromium replies — I/O, same shape as `await db.commit()` or TradingAgents' `readline()`, not CPU work happening in the Python process. So N concurrent scrapes (`#41`'s planned `Semaphore(3)`) means N Python coroutines interleaved on the single FastAPI event loop, each awaiting its own CDP round-trip — the pure single-thread cooperative case, no separate OS process per coroutine involved on the Python side at all.

Real parallelism for the scraper case exists, just one layer down: **inside** the one Chromium process's own internal multi-process architecture (a browser process plus roughly one renderer process per tab) — genuinely parallel page rendering/JS execution/network fetches, but entirely invisible to and unmanaged by Python. asyncio doesn't create that parallelism or coordinate it; it just fires CDP commands and waits for replies, interleaved.

| | TradingAgents | Scraper (Patchright) |
|---|---|---|
| OS process per unit of work | **Yes** — `create_subprocess_exec` per ticker | **No** — one Chromium process, launched once, reused |
| What "concurrent" means here | N independent OS processes in true parallel, each watched by a pair of pipe-reading `Task`s | N Python coroutines interleaved on one event loop, each awaiting CDP replies from tabs inside the *same* browser process |
| Where real parallelism happens | Directly — separate OS processes, separate cores | Indirectly — inside Chromium's own internal multi-process architecture |
| What bounds concurrency | DB partial unique index on `(ticker) WHERE status IN ('pending','running')` — no duplicate ticker, otherwise unbounded process count | `asyncio.Semaphore(3)` (`#41`, planned) — explicit, since unbounded tabs against one shared context risks real trouble (memory, the shared profile dir, site rate limits) |

### Terminology correction — "shared by processes" vs. "shared by coroutines within one process"

Came up clarifying `main.py`'s `event_queue` object (`asyncio.Queue`, distinct from `sse.py`'s per-connection queues) — worth stating precisely, since the word "shared" is easy to over-read given TradingAgents' actual subprocess use elsewhere in this same file.

`event_queue` is created once in `lifespan()` and handed to three places: `app.state.event_queue`, `poll_prices`'s job args, and `dispatcher.run()`. All three, plus every producer that later calls `.put()` on it (`jobs.py`'s `process_item`, `stocks.py`'s `FinnhubClient`, `#41`'s planned add-time trigger), are coroutines/`Task`s on **one event loop, in one OS process** — the same single-threaded cooperative model traced above. "Shared" here is ordinary Python reference semantics (multiple functions holding a reference to the same object, no different from passing a list around), not inter-process communication. Full producer/consumer breakdown: `.doc/architecture.md` → "Event-Driven Flow" → "One shared queue object, multiple producers, one sequential consumer."

Worth the explicit contrast precisely because this file's own TradingAgents section, right above, describes a case where "process" is literal — `create_subprocess_exec` really does spawn a separate OS process per analysis, needing pipes rather than a shared in-memory object. Don't let one section's "process" bleed into the other's — `event_queue`'s producers/consumer are never that.

# Challenges

## Synology DSM Storage API — 503 "Invalid session" (code 119) (2026-07-23)

**What happened (symptom):** `GET /api/system/storage` intermittently returned `503`, with the backend log showing:
```
Synology storage query failed: {'code': 119}
```
Confusing part: this happened *after* login had already reported success — the failure was on the follow-up storage-fetch call, not on `_login()` itself.

**What "the API" actually does underneath — not a single call.** From the browser's side, this looks like one request. In reality it's four hops, and the DSM leg alone is three separate calls, every single time:

```
Browser                Next.js proxy           FastAPI backend            Synology DSM
   │                         │                        │                        │
   │  GET /api/proxy/        │                        │                        │
   │  system/storage         │                        │                        │
   ├────────────────────────>│                        │                        │
   │                         │  GET /api/system/       │                        │
   │                         │  storage (+X-API-Key)   │                        │
   │                         ├───────────────────────>│                        │
   │                         │                        │  1. login (user/pass)  │
   │                         │                        ├───────────────────────>│
   │                         │                        │<───────────────────────┤
   │                         │                        │      sid returned      │
   │                         │                        │                        │
   │                         │                        │  2. fetch storage      │
   │                         │                        │     (uses sid)         │
   │                         │                        ├───────────────────────>│
   │                         │                        │<───────────────────────┤
   │                         │                        │    storage data        │
   │                         │                        │                        │
   │                         │                        │  3. logout (drops sid) │
   │                         │                        ├───────────────────────>│
   │                         │<───────────────────────┤                        │
   │<────────────────────────┤   storage JSON          │                        │
   │  storage JSON            │                        │                        │
```

One browser poll = one full login + fetch + logout cycle against DSM, repeated every 30 seconds, forever. This is *why* the race was even possible — each poll manufactures a brand-new, independent DSM session rather than treating "being logged in" as a standing state, so two overlapping polls mean two overlapping login/fetch/logout cycles, each capable of invalidating the other's sid.

**Why (root cause) — two things true at once:**

1. **DSM enforces one active session per `session=` name, per account.** A second `login` call using the same session name (`_DSM_SESSION_NAME = "webui"`, `backend/app/services/synology.py:11`) invalidates whatever sid an *earlier* login issued — even if that earlier sid is still mid-use. This mirrors normal browser session behavior (logging into the same web session from a new tab silently replaces the old one).

2. **`get_storage()` (`backend/app/services/synology.py:57`) had no coordination between concurrent calls.** Every call runs its own full login → fetch → logout cycle, with zero shared state — nothing in the code was aware that another call might already be mid-flight.

**The race, concretely:**
```
Request A (t=0.0s)   login → sid_A issued ✅
Request B (t=0.2s)   login (same session="webui") → sid_B issued, sid_A silently invalidated
Request A (t=0.3s)   fetch storage using sid_A → DSM: session invalid → code 119 ❌
Request B (t=0.4s)   fetch storage using sid_B → succeeds ✅
```
Whichever login happens last wins; anything still holding an earlier sid is now working with a dead credential. This produced intermittent failures (not every call — only when two requests happened to land close enough in time): the dashboard was open in a single tab, but occasional overlap (a slow round-trip letting the next 30s poll fire before the previous logout finished, or a dev-mode double effect) was enough to trigger it.

2FA was ruled out as a contributing cause (checked directly — not enabled on the account) — this is purely the concurrent-session race described above, see [[Concurrent Session Invalidation]] in Concepts for the general pattern and the decided solution.

**Status:** fixed. Applied to `backend/app/services/synology.py` — persistent cached `_sid`, `asyncio.Lock` scoped to `_get_sid`'s refresh step only, `_SessionExpired` raised specifically on DSM error codes 106/119 and caught by `get_storage()` for a single retry-with-relogin. `_logout` wired into a new `close()` method, called from `backend/app/main.py`'s `lifespan()` shutdown sequence alongside the existing `finnhub.stop()`. Not yet verified against the live NAS — next real DSM poll (or a container restart) will confirm.

## Rendering strategies — CSR, SSR (+ hydration), and RSC compared (2026-08-27)

Why this belongs here: surfaced debugging issue #50 (29CM's scraper returning the wrong price). Musinsa and 29CM disagree with each other not because of a scraper bug in the ordinary sense, but because the two retailers are built on genuinely different Next.js rendering models — worth understanding the mechanics once, generally, since it explains why one site's data fits in `__NEXT_DATA__` and the other's structurally can't.

### The four strategies, by how much work server vs. browser does

**1. CSR (Client-Side Rendering)** — classic single-page app (plain React/Vue, `create-react-app`). Server sends a near-empty HTML shell + a JS bundle. The browser downloads and executes that JS, and *that* JS builds the entire page client-side, including fetching data via API calls after the page has already "loaded." View-source shows almost nothing — no scraper without real JS execution (i.e. no plain `httpx` request) can read anything meaningful off a CSR page.

**2. Traditional SSR (+ hydration)** — the older model (Next.js Pages Router, `getServerSideProps`, most historical "SSR" frameworks). The server runs the *same* component code the browser would, producing full real HTML for the first response — good first paint, good SEO, and a plain HTTP scraper sees real content immediately. Concretely, same component:

```jsx
function ProductPage({ price }) {
  return <div>Price: ${price}</div>;
}
```

1. Request arrives at a Node.js server (a JS *runtime* on the server, not a browser).
2. Server calls something like `renderToString(<ProductPage price={310400} />)` — runs the component function in Node, producing a plain HTML string. No DOM exists yet anywhere; this is string generation.
3. That HTML string is sent to the browser as a complete document — real content, visible via plain HTTP fetch, no JS execution needed on the reader's end.
4. Browser's own HTML parser paints it immediately — fast, no JS required yet.
5. Browser downloads the JS bundle containing that same component's code, separately.
6. Once loaded, the browser calls the *same* `ProductPage({ price: 310400 })` function again — this time in the browser — and instead of replacing the existing DOM, React walks it and attaches event listeners/state to it. That's **hydration**: making already-painted static markup interactive, not repainting it.

For hydration to reproduce identical output, the server has to hand the browser the *data* it used (`price: 310400`) — not the code, the bundle already has that. That's what `__NEXT_DATA__` is: one JSON blob of props, serialized once, for the client's re-render pass to consume.

**3. RSC (React Server Components)** — Next.js App Router's current model. Splits components into two kinds:

| | Server Components (default) | Client Components (`"use client"`) |
|---|---|---|
| Where it runs | Server only | Server (first render) + browser (hydration) |
| JS shipped to browser | **None at all** | Yes, same as traditional SSR |
| Can touch DB/filesystem directly | Yes — no API layer needed | No — needs props from a server component or an API call |
| What's sent to the client | Serialized *output* (Flight rows) | Code + data, hydrates like #2 above |

A real page mixes both kinds. The server-only parts never get re-executed by the browser at all — no hydration pass for them, because their JS was never shipped in the first place. The browser only hydrates the "islands" of interactive Client Components.

**The conceptual shift from #2 to #3:** traditional SSR's server render is a *preview* — an optimization so the page isn't blank while the browser prepares to fully rebuild it via hydration. RSC's server render is *final* for the server-only parts — nothing rebuilds them. That's why RSC doesn't ship one big props blob the way `__NEXT_DATA__` does: there's no client-side reconstruction step needing all the data reassembled into one object. It ships a description of already-finished UI, piece by piece, as each piece becomes ready — a **stream** of small chunks (`self.__next_f.push(...)`, "Flight" being the internal codename for this wire protocol — `next_f` = "Next Flight"), each row addressable by an id, later rows able to *reference* earlier ones (`"$a7"`) instead of duplicating shared data. This lets a slow part (wrapped in `<Suspense>`) arrive as a later chunk without blocking everything else that was already ready — real 29CM product pages stream on the order of 90+ separate chunks this way.

### Why `og:price` and `__NEXT_DATA__` don't already cover RSC data

Three genuinely separate mechanisms, easy to conflate since they can all carry the same underlying value (a product's price):

| Mechanism | What it is | Who maintains it | Exists on... |
|---|---|---|---|
| `og:price` meta tag | Static Open Graph tag, originally for social-media link previews (Facebook/Twitter price cards) | SEO/marketing tooling — any framework, unrelated to Next.js entirely | Any site that bothers to add one |
| `__NEXT_DATA__` | Pages Router's one-shot props blob (see #2 above) | Next.js's older routing model | Pages Router pages only |
| RSC/Flight (`self.__next_f.push`) | App Router's streamed component output (see #3 above) | Next.js's current routing model | App Router pages only |

None of them "cover" the others — a page can have any combination, or none, and they're written by different parts of a site's stack at different times, which is exactly why they can *disagree*: musinsa's `og:price` meta reported a stale plain sale price while its own `__NEXT_DATA__` (the actual component-level data) had the accurate coupon price. A site's Next.js routing generation (Pages vs. App Router) determines whether `__NEXT_DATA__` exists **at all** — not a bug, not a missing tag, a different data-shipping mechanism entirely. Confirmed directly: musinsa's page has exactly one `<script id="__NEXT_DATA__">` tag; 29CM's has zero, only `self.__next_f.push(...)` chunks.

### Tie-in: why this repo needs two different scraper extraction methods

- **Musinsa** (Pages Router, or at least still emits `__NEXT_DATA__`) — one clean, `json.loads`-able JSON tree. `_extract_nextdata()` (`backend/app/services/scraper/base.py`) reads it directly.
- **29CM** (App Router, RSC/Flight streaming) — no such single tree exists. The real discounted price is genuinely present in the initial HTTP response (the page *is* server-rendered — this doesn't require a real browser/Patchright, no client-side JS execution needed), just encoded as ~90 cross-referencing stream chunks instead of one object. Needs its own parser (`_extract_rsc_flight()`, tracked as issue #50, `.doc/issues.md`) — concatenate the chunk payloads, split into rows, resolve `"$rowId"` references, then reuse the same priority-key/ID-scoping search machinery `_extract_nextdata()` already has, rather than reinventing it.

Both sites are legitimately server-rendering their price data — the difference is entirely in *which* Next.js data-shipping mechanism each one happens to use, not in how "scrapeable" one is versus the other.
