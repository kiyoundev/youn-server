// Wealthsimple activity import (issue #33). Goes through the dedicated
// multipart proxy route (api/proxy/activities/import/route.ts), not the JSON
// catch-all — same reason as there: the backend's X-API-Key must never reach
// the browser.
import { ApiError } from "@/lib/api/items";

// Mirrors backend/app/schemas/activity.py.
export interface AccountImportResult {
  account_id: string;
  added: number;
  replaced: number;
  skipped: number;
  coverage: { earliest: string; newest: string };
  message: string;
  warnings: string[];
}

export interface ImportResult {
  accounts: AccountImportResult[];
}

// Error `detail` comes back in several shapes: an object for this route's own
// rejections ({code, message, ...extras} — LedgerImportError), an array for
// FastAPI's own validation errors, a plain string from the proxy's
// misconfiguration 500, or nothing parseable at all. ApiError.detail stays a
// plain string (every other call site passes it straight to toast.error), so
// this collapses whichever shape arrived into one readable message.
function messageFromDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  return `Request failed with status ${status}`;
}

export async function importActivities(file: File): Promise<ImportResult> {
  const formData = new FormData();
  formData.append("file", file);

  // Deliberately no `headers`: the browser sets Content-Type itself, with the
  // multipart boundary in it. Setting it here (or reusing items.ts's
  // request(), which forces application/json) would leave the backend unable
  // to find where the file starts and ends.
  const res = await fetch("/api/proxy/activities/import", { method: "POST", body: formData });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    // The toast shows only the message, but a rejection's extras (e.g.
    // unknown_activity_type's `types` list — the exact strings needed to add
    // a mapping) stay retrievable from the console.
    if (detail && typeof detail === "object") console.error("Activity import rejected:", detail);
    throw new ApiError(res.status, messageFromDetail(detail, res.status));
  }

  return res.json();
}
