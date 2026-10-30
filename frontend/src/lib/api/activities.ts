// Wealthsimple activity import (issue #33). Goes through the dedicated
// multipart proxy route (api/proxy/activities/import/route.ts), not the JSON
// catch-all — same reason as there: the backend's X-API-Key must never reach
// the browser.
import { ApiError, messageFromDetail } from "@/lib/api/api-client";

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
