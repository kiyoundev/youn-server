// Multi-tab dedup for the watchlist's SSE stream. Every mounted tab calls
// subscribeToListingEvents() the same way — which tab actually holds the
// real EventSource is decided by the browser's Web Locks queue, not by
// anything this module's caller has to know or manage.
//
// Why this exists at all: browsers cap concurrent connections to one origin
// at 6 under HTTP/1.1 (this stack's actual deployment shape today — no
// TLS/HTTP2 in front, see docker-compose.yml). Without dedup, N open tabs of
// /watchlist would open N real connections, competing with every other
// request to this origin for that same budget. Full comparison against
// SharedWorker (ruled out — no iOS Safari support) and an infra-level fix:
// .doc/keynotes.md.

export type ListingChangedEvent = { product_id: number; listing_id: number };
export type ConnectionStatus = "online" | "unavailable";

interface SubscribeHandlers {
  onEvent: (payload: ListingChangedEvent) => void;
  onStatusChange: (status: ConnectionStatus) => void;
}

type RelayMessage = { kind: "event"; data: string } | { kind: "status"; status: ConnectionStatus };

const LOCK_NAME = "watchlist-sse-leader";
const CHANNEL_NAME = "watchlist-sse-relay";
const RECONNECT_INITIAL_MS = 1000;
const RECONNECT_MAX_MS = 60000; // same shape as backend/app/services/stocks.py's FinnhubClient._listen()

export function subscribeToListingEvents(handlers: SubscribeHandlers): () => void {
  let closed = false;
  let es: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let backoff = RECONNECT_INITIAL_MS;
  let releaseLock: (() => void) | null = null;

  // Followers receive relayed events/status here; the leader tab never
  // receives its own postMessage back (BroadcastChannel doesn't loop a
  // sender's own messages to itself), so no "am I the leader" check needed.
  const channel = new BroadcastChannel(CHANNEL_NAME);
  channel.onmessage = (e: MessageEvent<RelayMessage>) => {
    const msg = e.data;
    if (msg.kind === "event") handlers.onEvent(JSON.parse(msg.data));
    else handlers.onStatusChange(msg.status);
  };

  const relay = (msg: RelayMessage) => channel.postMessage(msg);

  const setStatus = (status: ConnectionStatus) => {
    handlers.onStatusChange(status);
    relay({ kind: "status", status });
  };

  function connect() {
    if (closed) return;
    es = new EventSource("/api/proxy/events/stream");

    es.onopen = () => {
      backoff = RECONNECT_INITIAL_MS;
      setStatus("online");
    };

    es.onmessage = (e: MessageEvent<string>) => {
      handlers.onEvent(JSON.parse(e.data));
      relay({ kind: "event", data: e.data });
    };

    es.onerror = () => {
      // Manually closing hands full control to the backoff loop below —
      // otherwise the browser's own native fixed-interval auto-reconnect
      // would race with this one (plan explicitly avoids relying on it).
      es?.close();
      es = null;
      setStatus("unavailable");
      reconnectTimer = setTimeout(() => {
        backoff = Math.min(backoff * 2, RECONNECT_MAX_MS);
        connect();
      }, backoff);
    };
  }

  const abortController = new AbortController();
  navigator.locks
    .request(LOCK_NAME, { signal: abortController.signal }, () => {
      // Holds the lock until this promise resolves — resolved only by
      // cleanup below, on tab close/crash the browser resolves it for us
      // and promotes the next queued tab automatically.
      //
      // The `closed` check matters: cleanup can run before this callback
      // ever fires (lock grants are always async, never synchronous — under
      // React StrictMode's dev-only mount→cleanup→mount double-invoke,
      // cleanup routinely runs while releaseLock is still null, so it takes
      // the abortController.abort() branch below instead). If the browser
      // still grants this now-aborted request anyway — a narrow ordering
      // race, not guaranteed prevented by abort() — releasing immediately
      // here is what stops it from holding the lock forever with nothing
      // running: cleanup already ran once and won't run again, so nothing
      // would ever call resolve() otherwise, deadlocking every other tab's
      // pending request behind a lock nobody's using.
      return new Promise<void>((resolve) => {
        if (closed) {
          resolve();
          return;
        }
        releaseLock = resolve;
        connect();
      });
    })
    .catch((err: unknown) => {
      // AbortError is expected when cleanup fires before this tab ever won
      // the lock (still queued as a follower) — not a real failure.
      if (err instanceof Error && err.name === "AbortError") return;
      // Anything else is a genuine, unexpected failure to even request the
      // lock — surface it through the same status path callers already
      // handle, rather than letting it become a silent unhandled rejection.
      console.error("subscribeToListingEvents: lock request failed", err);
      setStatus("unavailable");
    });

  return () => {
    closed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    es?.close();
    channel.close();
    if (releaseLock) {
      releaseLock(); // was leader — release so another tab can be promoted
    } else {
      abortController.abort(); // still queued as follower — cancel the pending request
    }
  };
}
