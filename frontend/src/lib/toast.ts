import { toast as toastManager } from "@/components/ui/toast";

// Sonner-style success()/error() sugar over the registry's own toast
// manager (components/ui/toast.tsx exports `toast`, the createToastManager()
// singleton that <Toaster/> is wired to by default via its toastManager
// prop's default value). Importing that same instance here — rather than
// creating a second createToastManager() — is what makes calls from this
// file actually show up in the mounted <Toaster/>; a second instance would
// silently go nowhere. `type` drives both the icon (ToastIcon) and styling
// (data-[type=...] selectors) already built into the generated component.
export const toast = {
  success: (title: string) => toastManager.add({ title, type: "success" }),
  // persist: true -> timeout: 0, which ToastObject documents as "prevent the
  // toast from being dismissed automatically" — used for the add-item
  // background chain's failure summary, since it can resolve well after the
  // user's attention has moved elsewhere (dialog already closed).
  error: (title: string, opts?: { persist?: boolean }) =>
    toastManager.add({ title, type: "error", ...(opts?.persist ? { timeout: 0 } : {}) }),
};
