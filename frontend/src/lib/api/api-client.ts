// Shared HTTP layer for every lib/api/* module: one ApiError class and one
// request() wrapper around fetch, so a call site can branch on
// `err instanceof ApiError` no matter which module threw it.

// Thrown on any non-2xx response so callers can branch on status (e.g. 409
// -> "already watched" toast vs. a generic failure toast) instead of every
// call site re-parsing the response body by hand.
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

// Error `detail` comes back in several shapes: an object for routes that
// reject with a code ({code, message, ...extras} — LedgerImportError), an
// array for FastAPI's own validation errors, a plain string from most routes
// and from the proxy's misconfiguration 500, or nothing parseable at all.
// ApiError.detail stays a plain string (every call site passes it straight to
// toast.error), so this collapses whichever shape arrived into one readable
// message.
export function messageFromDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  return `Request failed with status ${status}`;
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  // pass the caller's options through
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });

  // turn HTTP errors into ApiError exceptions
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, messageFromDetail(body?.detail, res.status));
  }

  // DELETE routes return 204 with no body — nothing to parse.
  if (res.status === 204) return undefined as T; // no body to parse
  return res.json(); // parse and hand back as T
}
