# PRD: youn-server — Price & Stock Alert Notification System

## Problem Statement

As a personal user tracking product prices and stock tickers across multiple devices, I have no single self-hosted system that watches for price drops or stock threshold crossings and immediately notifies me across all my Apple devices. Existing third-party services are either subscription-based, cloud-only, lack Apple Watch support, or cannot trigger downstream automation like AI-driven market analysis when a stock hits a target price.

## Solution

A self-hosted notification system running on a Raspberry Pi 5 that:

1. Monitors a wishlist of product URLs across Canadian retailers (Amazon.ca, BestBuy.ca, Walmart.ca, others) and alerts when a price drops to or below a user-defined target.
2. Monitors a watchlist of stock tickers in real-time via Finnhub WebSocket and alerts when prices cross user-defined thresholds in a chosen direction (above/below).
3. Delivers alerts natively via Pushover (iPhone, iPad, Mac, Apple Watch) and Gmail email.
4. Optionally triggers TradingAgents AI analysis as a decoupled downstream reaction when a stock threshold is crossed.
5. Exposes a Next.js dashboard for managing watchlists and viewing price history.

## User Stories

1. As a user, I want to add a product URL with a target price to my wishlist, so that I am notified when the price drops to my desired level.
2. As a user, I want to edit a wishlist item's target price, so that I can adjust my alert threshold without re-adding the item.
3. As a user, I want to pause a wishlist item without deleting it, so that I can temporarily stop monitoring it while preserving its history.
4. As a user, I want to delete a wishlist item, so that I can remove products I'm no longer interested in.
5. As a user, I want to view the price history chart for a wishlist item, so that I can see how the price has trended over time.
6. As a user, I want Amazon.ca products to be automatically detected from their URL, so that I don't need to manually specify the retailer.
7. As a user, I want scraping to work on JavaScript-rendered retailer pages, so that prices are reliably extracted even from dynamic storefronts.
8. As a user, I want to add a stock ticker with a target price and direction (above/below) to my stock watchlist, so that I am alerted when the stock crosses my threshold.
9. As a user, I want the system to validate a ticker symbol when I add it, so that I can't accidentally save an invalid ticker.
10. As a user, I want to update a stock alert's target price or direction, so that I can adjust my threshold as market conditions change.
11. As a user, I want to pause or delete a stock alert, so that I can manage my watchlist over time.
12. As a user, I want stock prices monitored in real-time via Finnhub WebSocket, so that alerts fire immediately when a threshold is crossed.
13. As a user, I want product prices to be polled every 6 hours, so that I catch price drops without triggering retailer bot detection.
14. As a user, I want to receive a native push notification on my iPhone when an alert fires, so that I see it immediately without checking any app.
15. As a user, I want the push notification to mirror to my Apple Watch, so that I'm alerted even when my phone is not in hand.
16. As a user, I want push notifications delivered to my iPad and Mac as well, so that I'm covered across all my Apple devices.
17. As a user, I want to receive an email notification alongside the push, so that I have a persistent record of alerts.
18. As a user, I want the email to include the item name, current price, target price, and a direct link to the product, so that I can act on it immediately.
19. As a user, I want alerts to not repeat on every poll cycle if the price is still below target, so that I'm not spammed.
20. As a user, I want the alert to re-arm once the price recovers above the target, so that I'm notified again if it drops a second time.
21. As a user, I want to optionally enable AI analysis (TradingAgents) for a specific stock alert, so that when the threshold is crossed an AI report is automatically generated.
22. As a user, I want the AI analysis to run asynchronously without blocking notifications, so that I receive the price alert immediately and the analysis report follows when complete.
23. As a user, I want to manually trigger AI analysis for any stock ticker at any time, so that I can get an on-demand report without waiting for a threshold crossing.
24. As a user, I want to view past AI analysis results for a stock from the dashboard, so that I can review historical reports.
25. As a user, I want to receive a follow-up push notification when AI analysis completes, so that I know the report is ready to review.
26. As a user, I want to manually trigger a price scraping job from the dashboard, so that I can force an immediate check without waiting for the next scheduled poll.
27. As a user, I want to manually trigger a stock price poll from the dashboard, so that I can verify a threshold immediately after adding a new stock alert.
28. As a user, I want all API routes protected by a shared API key, so that my watchlist data cannot be read or modified by others on the same network.
29. As a user, I want the system to auto-start on Pi reboot, so that alerts continue without manual intervention after a power outage.
30. As a user, I want the system to run entirely on my home hardware with no ongoing cloud costs, so that it remains free to operate.
31. As a user, I want to see the top 10 trending stocks and ETFs plus major indices on my portfolio page, so that I can spot popular assets without searching for them.
32. As a user, I want to click any ticker on my portfolio page (a holding, a watchlist alert, or a trending asset) and see its full chart and market details, so that I can research it without leaving the app.

## Implementation Decisions

### Modules

**RetailerRouter + Scraper Hierarchy**
Abstract `BaseScraper` with a `get_price(url) -> float | None` interface. Three implementations: `HTTPScraper` (httpx + BeautifulSoup4 for SSR retailers), `PlaywrightScraper` (headless Chromium for JS-rendered pages), and `AmazonCAScraper` extending `PlaywrightScraper` with Amazon-specific selectors and playwright-stealth masking. `RetailerRouter` maps URL domains to scraper classes via a config dict — adding a new retailer is a config change, not a code change. CSS selectors are stored in a separate config dict, not hardcoded in scraper classes.

**StockPriceService**
`FinnhubClient` maintains a persistent WebSocket connection to Finnhub. Subscribes/unsubscribes to tickers dynamically as `StockAlert` rows are created, updated, or deleted. On each price tick, checks all active `StockAlert` thresholds — fires an event if crossed. Finnhub REST (`/api/v1/quote`) is the fallback for ticker validation and one-off price queries (manual poll trigger endpoint). yfinance is used exclusively for dashboard price history charts via `Ticker.history()`. All external calls wrapped in try/except; returns None on failure.

**EventQueue (transactional outbox + asyncio.Queue)**
Producers write an `Event` row to the DB (`status="pending"`) and immediately put it on an in-memory `asyncio.Queue`. Consumers are queue listeners — zero-latency delivery, no polling. On startup, any `status="pending"` rows are loaded back into the queue to recover from crashes. Event `payload` stores a full snapshot so consumers never re-query the DB to process an event.

**NotifyService**
Single `send_alert(title, body, url)` entry point that dispatches to Pushover and email independently. Pushover: one HTTP POST to `api.pushover.net` using `PUSHOVER_APP_TOKEN` + `PUSHOVER_USER_KEY` from `.env` — reaches all Apple devices simultaneously. Email: smtplib STARTTLS to Gmail. Failure of one channel does not block the other.

**AnalysisConsumer + TradingAgents Wrapper**
`AnalysisConsumer` reads `STOCK_THRESHOLD` events from `asyncio.Queue`, checks `StockAlert.run_analysis`, and if true spawns TradingAgents as an async subprocess via `asyncio.create_subprocess_exec`. Captures stdout, parses structured output, stores in `AnalysisResult` table. Sends follow-up push notification on completion. `run_analysis` is off by default — opt-in per stock alert.

**APScheduler Jobs**
In-process `AsyncIOScheduler` started on FastAPI `lifespan`. Two jobs: price scrape (every 6 hours), consumer startup (queue listeners started once on lifespan, not on a schedule). Manual trigger endpoints call the same job functions directly.

**FastAPI Routers**
CRUD routers for: `Product`/`Listing` (wishlist), `StockAlert`, manual poll triggers, and AI analysis. All routes protected by `verify_api_key` dependency except `GET /api/health`. CORS origin configured via env var.

**Next.js Dashboard**
App Router pages: Wishlist (table + price history chart via recharts), Stocks (table with analysis toggle), Analysis (results viewer). All API calls proxied through Next.js route handlers — API key never reaches the browser.

### Schema

Six models: `Product`, `Listing` (one product, many retailer listings — table name `watch_items`, predates the split), `PriceHistory`, `StockAlert` (with `run_analysis: bool`), `Event`, `AnalysisResult`. Postgres via asyncpg. Alembic manages migrations.

### Architecture Pattern

Embedded APScheduler (Pattern 1) as the clock for scraping. Finnhub WebSocket for real-time stock price monitoring. Transactional outbox + `asyncio.Queue` for decoupled consumer reactions — producers write events to DB and queue; consumers listen on the queue and mark events processed. This separates "detecting a threshold crossing" from "what to do about it."

### Security

Shared API key (`X-API-Key` header). `.env` volume-mounted with `chmod 600`. Containers run as non-root. Network access via Tailscale only — Pi not exposed to the internet.

### Deployment

Docker Compose on Raspberry Pi 5 8GB (ARM64). Playwright uses `mcr.microsoft.com/playwright/python` base image for reliable ARM64 Chromium. Postgres runs in Docker on Synology NAS (same home LAN). TradingAgents cloned separately at `/opt/tradingagents` on Pi host.

## Testing Decisions

Good tests verify external behaviour through the module's public interface, not implementation details. They do not mock the module under test — only its external dependencies (network calls, subprocesses, filesystem).

**Modules to test:**

- **RetailerRouter** — given a URL, assert correct scraper class is returned; assert unknown domains fall back to HTTPScraper. No network calls needed.
- **HTTPScraper** — mock httpx responses; assert correct price extracted for each retailer's HTML fixture; assert None returned on connection error or missing selector.
- **StockPriceService** — mock Finnhub WebSocket messages; assert threshold detection fires correct event; assert deduplication blocks second event when `alerted_at` is set; assert re-arm clears `alerted_at` on price recovery; mock Finnhub REST for `validate_ticker` tests; mock yfinance `Ticker.history()` for price history tests; assert Finnhub REST failure returns None without raise.
- **EventQueue consumer logic** — put pending Event objects on a real `asyncio.Queue`; run consumer; assert events are consumed and marked `processed` in a real Postgres test DB; assert correct downstream calls made.
- **NotifyService Pushover sender** — mock httpx; assert correct token, user key, title, body, and url fields sent; assert email fallback runs independently.
- **Alert deduplication** — assert second tick with price still below target does not produce a second Event when `alerted_at` is set; assert re-arm clears `alerted_at` when price recovers.
- **API routes (integration)** — spin up FastAPI test client with a real Postgres test DB; assert CRUD operations produce correct DB state and response shapes; assert 401 on missing API key; assert 409 on duplicate analysis trigger.

## Out of Scope

- Multi-user support or user accounts
- HTTPS on the Pi (traffic is Tailscale-encrypted)
- Real-time WebSocket price streaming to the dashboard (dashboard uses 30-second SWR polling)
- Secrets manager (`.env` file is sufficient at personal scale)
- Redis, Celery, or any external message broker
- Native Apple Watch app (Watch mirrors iPhone notifications via Pushover automatically)
- Support for retailers outside Canada (initial scope is `.ca` domains)
- Automated TradingAgents installation — cloned manually on Pi
- Native APNs (Pushover handles push delivery)
- iOS SwiftUI device registration app (not needed — Pushover requires no per-device token management)

## Further Notes

- **Finnhub WebSocket**: Free tier supports real-time trades for all tickers. On reconnect, re-subscribe all active `StockAlert` tickers. Implement exponential backoff on connection failure.
- **yfinance instability**: Yahoo Finance has broken yfinance without warning in the past. Used only for dashboard price history charts (`Ticker.history()`) — never on the hot path. Finnhub REST handles ticker validation and one-off price queries. A `GET /api/health/stocks` endpoint should verify Finnhub WebSocket is connected.
- **Amazon.ca scraping**: Amazon's bot detection is aggressive. `playwright-stealth` is the first mitigation; graceful skip (log warning, no crash) is the fallback if scraping fails after 2 retries.
- **Playwright on ARM64**: Use the `mcr.microsoft.com/playwright/python` Docker image rather than installing Chromium inside a generic Python image — ARM64 Chromium builds from `playwright install` have been unreliable.
- **TradingAgents costs**: Runs LLM API calls (likely OpenAI or Anthropic). Costs real money per analysis. Keep `run_analysis` off by default and document the cost implication clearly in the dashboard UI toggle.
- **Tailscale**: Required for off-LAN dashboard access and API calls. Free for personal use (up to 100 devices).
