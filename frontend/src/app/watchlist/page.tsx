"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { createPortal } from "react-dom";
import useSWR, { mutate } from "swr";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { PriceSparkline } from "@/components/ui/price-sparkline";
import { ProductPriceChart } from "@/components/ui/product-price-chart";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ExternalLink, LoaderCircle, MoreVertical, Plus, RefreshCw, Search, Pencil, Trash2, ClockAlert } from "lucide-react";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { LoadingScreen } from "@/components/ui/loading-screen";
import { cn } from "@/lib/utils";
import { useNavSlot } from "@/components/nav-slot";
import { useListingHistory, bucketByLocalDay, listingHistoryKey } from "@/lib/hooks/use-listing-history";
import { subscribeToListingEvents, type ConnectionStatus } from "@/lib/sse-leader";
import { fmtPrice, fmtCadEquivalent, toCad } from "@/lib/format";
import {
  createProduct,
  createListing,
  updateProduct,
  updateListing,
  deleteListing,
  deleteProduct,
  pollAllPrices,
  pollProduct,
  ApiError,
  getFxRates,
  type Product,
  type Listing,
  type WatchStatus,
  type FxRates,
} from "@/lib/api/items";
import { toast } from "@/lib/toast";

// null when every listing's last_price is null (e.g. every retailer OOS/errored) —
// callers render a "—" fallback rather than treating this as 0.
const bestPrice = (product: Product): number | null => {
  const prices = product.listings.map((l) => l.last_price).filter((p): p is number => p !== null);
  return prices.length > 0 ? Math.min(...prices) : null;
};

type HistoryPoint = { date: string; price: number };

// Min across a product's listings, per local calendar day — each listing's
// points must already be bucketed by bucketByLocalDay() before reaching
// here (see challenges.md #3: merging before bucketing silently degrades
// "min across retailers" to "whichever listing happened to be scraped at
// that instant").
const mergeMinByDay = (listings: Listing[], historyByListing: Record<number, HistoryPoint[]>): HistoryPoint[] => {
  const allPoints = listings.flatMap((l) => historyByListing[l.id] ?? []);
  const dates = Array.from(new Set(allPoints.map((p) => p.date))).sort();
  return dates.map((date) => {
    const pricesOnDate = allPoints.filter((p) => p.date === date).map((p) => p.price);
    return { date, price: Math.min(...pricesOnDate) };
  });
};

const STATUS_BADGE: Record<
  WatchStatus,
  {
    label: string;
    variant: "default" | "secondary" | "outline" | "destructive";
  }
> = {
  watching: { label: "Watching", variant: "secondary" },
  triggered: { label: "Triggered", variant: "default" },
  paused: { label: "Paused", variant: "outline" },
  failed: { label: "Failed", variant: "destructive" },
  processing: { label: "Processing", variant: "outline" },
};

// Mirrors backend's compute_status() priority order (product_status.py) —
// exists so the sheet-panel badge can reflect the draft active toggle
// immediately, before Save persists it (found live: flipping the switch
// updated the switch itself but not the badge next to it, since the badge
// was reading product.status, real server truth, with no draft-awareness
// at all). Can't replicate compute_status()'s in-flight-scrape signal
// (scrape_tracking.py — process-local, backend-only, no field on the
// frontend Product type to read) — toggling mid-scrape may show a stale
// non-"processing" state for a moment until the next refetch, same
// tradeoff every other draft field here already accepts. Only used for
// this one preview; the table row's own badge stays on product.status
// (real truth) unconditionally.
function draftStatus(product: Product, active: boolean): WatchStatus {
  if (!active) return "paused";
  if (product.listings.some((l) => l.last_scrape_status === null)) return "processing";
  if (product.listings.some((l) => l.last_scrape_status === "error")) return "failed";
  if (product.alerted_at !== null) return "triggered";
  return "watching";
}

const formatLastChecked = (iso: string | null) => {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMinutes = Math.round(diffMs / (1000 * 60));
  if (diffMinutes < 1) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
};

function fmtValue(value: number) {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

// Issue #45 — reused next to the header total and inside the sheet panel
// wherever a CAD-converted figure is shown; title gives a hover
// explanation (native tooltip, no new UI dependency for a single icon).
function StaleFxIcon() {
  return (
    <span title="FX rate may be out of date — showing the last known rate" aria-label="FX rate may be stale">
      <ClockAlert className="size-3.5 text-muted-foreground" aria-hidden="true" />
    </span>
  );
}

const emptyNewItem = { name: "", targetPrice: "", urls: "" };

const fetcher = (url: string) => fetch(url).then((r) => r.json());

// Well-formed AND http(s)-only — rejects javascript:/data: schemes before a
// URL ever reaches an <a href>. No visual per-line indicator; this only
// gates whether a save action (dialog button or inline Enter) is allowed.
const isValidUrl = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
};

// Which single retailer listing in the currently-open sheet is being
// edited, if any — modeled as one state so switching modes always replaces
// the whole thing rather than relying on every handler to reset every
// other flag by hand. Only retailer add/edit stays on this immediate-
// commit pattern (issue #45 follow-up) — those have real side effects (a
// scrape dispatch, cascading price-history deletion on remove) a Cancel
// can't honestly undo the way a plain text-field revert can. Product-level
// fields (name/target_price/active) moved to the batched ProductDraft
// below instead, mirroring market/[ticker]/page.tsx's AlertDraft pattern.
type SheetEditState = { type: "none" } | { type: "listing"; id: number; draft: string } | { type: "addingListing"; draft: string };

type SheetEditAction =
  | { type: "editListing"; id: number; url: string }
  | { type: "addListing" }
  | { type: "setDraft"; draft: string }
  | { type: "cancel" };

function sheetEditReducer(state: SheetEditState, action: SheetEditAction): SheetEditState {
  switch (action.type) {
    case "editListing":
      return { type: "listing", id: action.id, draft: action.url };
    case "addListing":
      return { type: "addingListing", draft: "" };
    case "setDraft":
      return state.type === "none" ? state : { ...state, draft: action.draft };
    case "cancel":
      return { type: "none" };
  }
}

// Product-level batched edit draft (name/target_price/active) — mirrors
// market/[ticker]/page.tsx's AlertDraft/isSectionDirty/saveSection
// pattern exactly: nothing here reaches the network on its own; only the
// sheet-level Save diffs it against the real product and fires one PATCH
// with just the changed fields.
type ProductDraft = {
  name: string;
  target_price: string;
  active: boolean;
};

function draftFromProduct(product: Product): ProductDraft {
  return {
    name: product.name ?? "",
    target_price: String(product.target_price),
    // No raw `active` field on the frontend Product type (compute_status
    // folds it into `status` server-side) — derived the same way the
    // pre-batch Switch's `checked` prop already was.
    active: product.status !== "paused",
  };
}

// Same guard the pre-batch per-field-commit code applied before every
// mutation (`if (!(target_price > 0)) return;`) — reinstated here so a
// bad/empty string can't register as "dirty" or reach updateProduct as NaN.
function parseValidPrice(raw: string): number | null {
  if (raw.trim() === "") return null;
  const price = Number(raw);
  return Number.isFinite(price) && price > 0 ? price : null;
}

function isProductDirty(product: Product, draft: ProductDraft): boolean {
  const trimmedName = draft.name.trim();
  const price = parseValidPrice(draft.target_price);
  // Truthy-gated, matching saveProduct's own guard below — an emptied
  // name never actually gets sent (same "can't clear via this path"
  // behavior the old immediate-commit code already had), so it must not
  // register as dirty either. Without this, Save could enable, "succeed,"
  // and close the sheet having silently sent nothing at all.
  const nameChanged = trimmedName !== "" && trimmedName !== (product.name ?? "");
  const priceChanged = price !== null && price !== product.target_price;
  const activeChanged = draft.active !== (product.status !== "paused");
  return nameChanged || priceChanged || activeChanged;
}

// Fires one updateProduct call with only the fields that actually changed —
// same diff-against-real-state shape as market/[ticker]/page.tsx's
// saveSection(). Caller (handleSave) only invokes this when isProductDirty
// already returned true, so "nothing to send" isn't a case reachable here
// in practice, but the empty-payload guard stays anyway — cheap, and
// avoids a no-op network call if that ever changes.
async function saveProduct(product: Product, draft: ProductDraft) {
  const payload: Parameters<typeof updateProduct>[1] = {};
  const trimmedName = draft.name.trim();
  if (trimmedName && trimmedName !== (product.name ?? "")) payload.name = trimmedName;
  const price = parseValidPrice(draft.target_price);
  if (price !== null && price !== product.target_price) payload.target_price = price;
  const activeChanged = draft.active !== (product.status !== "paused");
  if (activeChanged) payload.active = draft.active;
  if (Object.keys(payload).length > 0) {
    await updateProduct(product.id, payload);
  }
}

// Renders nothing — its only job is to hold exactly one useListingHistory
// call (rules-of-hooks requires a fixed hook count per component instance;
// a product's listing count varies, so each listing gets its own instance
// of this rather than looping the hook directly) and report the bucketed
// result up to the row that mounted it.
function ListingHistoryFetcher({ listing, onData }: { listing: Listing; onData: (listingId: number, points: HistoryPoint[]) => void }) {
  const { data } = useListingHistory(listing.product_id, listing.id);

  useEffect(() => {
    if (data) onData(listing.id, bucketByLocalDay(data));
  }, [data, listing.id, onData]);

  return null;
}

function ProductRow({
  product,
  openId,
  setOpenId,
  editState,
  dispatchEdit,
  chartReady,
  fxRates,
  fxStale,
}: {
  product: Product;
  openId: number | null;
  setOpenId: (id: number | null) => void;
  editState: SheetEditState;
  dispatchEdit: (action: SheetEditAction) => void;
  chartReady: boolean;
  // Issue #45 — {} before the first successful FX refresh (bootstrap
  // case), not undefined/loading-gated — toCad()/fmtCadEquivalent()
  // already handle a missing rate by returning null, so the sheet panel
  // just quietly shows no CAD-equivalent suffix until rates land.
  fxRates: Record<string, number>;
  fxStale: boolean;
}) {
  // Mounted unconditionally with the row (not gated by the sheet being
  // open), so history is already warm by the time this row's sheet opens —
  // the only way to reach it is through this row, so it's already mounted.
  const [historyByListing, setHistoryByListing] = useState<Record<number, HistoryPoint[]>>({});
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  // Issue #51 — covers just the click-to-response gap; product.status
  // becoming "processing" (via the in-flight set, once the SSE update
  // lands) is what keeps the button disabled for the actual scrape
  // duration after that. Without this, a second click during the brief
  // window before the first SSE event arrives could slip past the
  // server's own in-flight/cooldown guards' timing and still show as an
  // instant, confusing no-op on the button itself.
  const [isPolling, setIsPolling] = useState(false);

  const handleHistoryData = useCallback((listingId: number, points: HistoryPoint[]) => {
    setHistoryByListing((prev) => ({ ...prev, [listingId]: points }));
  }, []);

  // Batched name/target_price/active edit draft (issue #45 follow-up).
  // Reset to current server truth only when this row's sheet opens — not
  // every time the underlying SWR poll refreshes while it's open, or an
  // in-progress edit would get silently blown away mid-session (same
  // reasoning as market/[ticker]/page.tsx's identical effect).
  const isSheetOpen = openId === product.id;
  const [draft, setDraft] = useState<ProductDraft>(() => draftFromProduct(product));
  const [isSaving, setIsSaving] = useState(false);
  // Display-vs-edit toggle per field, same look as before batching — the
  // draft/Save/Cancel machinery underneath doesn't care which way the
  // display works; typing into either just writes to `draft`, never
  // commits on its own. Separate booleans, not folded into the
  // SheetEditState reducer above — that one's scoped to retailers only.
  const [isEditingName, setIsEditingName] = useState(false);
  const [isEditingTargetPrice, setIsEditingTargetPrice] = useState(false);
  // Retailer add/edit/delete stay immediate/separate (see SheetEditState
  // above) — they've already persisted the moment they happen, so Save
  // has nothing further to do for them. This just tracks "did anything
  // happen in this sheet session" so the Save button also enables as a
  // way to acknowledge/close out after retailer-only changes, not just
  // scalar-field edits.
  const [hasRetailerActivity, setHasRetailerActivity] = useState(false);
  useEffect(() => {
    if (isSheetOpen) {
      setDraft(draftFromProduct(product));
    } else {
      setIsEditingName(false);
      setIsEditingTargetPrice(false);
      setHasRetailerActivity(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSheetOpen]);
  const dirty = isProductDirty(product, draft) || hasRetailerActivity;

  const handleCancelEdits = () => {
    setDraft(draftFromProduct(product));
    setIsEditingName(false);
    setIsEditingTargetPrice(false);
    setHasRetailerActivity(false);
    setOpenId(null);
  };

  const handleSaveEdits = async () => {
    setIsSaving(true);
    try {
      await saveProduct(product, draft);
      await mutate("/api/proxy/items");
      toast.success("Updated");
      setOpenId(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to save changes");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteProduct = async () => {
    try {
      await deleteProduct(product.id);
      await mutate("/api/proxy/items");
      if (openId === product.id) setOpenId(null);
      toast.success("Item deleted");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to delete item");
    } finally {
      setIsDeleteDialogOpen(false);
    }
  };

  // Issue #51 — no mutate() call here, unlike the handlers above: this
  // product's own listings turning "processing" then resolving happens via
  // the existing SSE flow (subscribeToListingEvents -> mutate) as the
  // background scrape actually runs, not as a direct result of this POST
  // resolving (which only means the scrape was queued, not finished).
  const handleRescrapeProduct = async () => {
    setIsPolling(true);
    try {
      await pollProduct(product.id);
      toast.success("Rescraping…");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to trigger rescrape");
    } finally {
      setIsPolling(false);
    }
  };

  const status = STATUS_BADGE[product.status];
  // Sheet-panel-only badge preview, draft-aware (see draftStatus above) —
  // the table row's own badge above stays on `status`/product.status
  // unconditionally, real server truth only.
  const sheetStatus = STATUS_BADGE[draftStatus(product, draft.active)];
  const best = bestPrice(product);
  const sparklineData = mergeMinByDay(product.listings, historyByListing);
  // Chart wants per-retailer series, unmerged — same underlying per-listing
  // data as the sparkline above, just not min-merged across listings.
  const chartListings = product.listings.map((l) => ({
    retailer: l.retailer,
    priceHistory: historyByListing[l.id] ?? [],
  }));

  return (
    <>
      {product.listings.map((listing) => (
        <ListingHistoryFetcher key={listing.id} listing={listing} onData={handleHistoryData} />
      ))}
      <Sheet open={openId === product.id} onOpenChange={(open) => setOpenId(open ? product.id : null)}>
        <TableRow className="cursor-pointer" onClick={() => setOpenId(product.id)}>
          <TableCell className="font-medium">{product.name ?? "Untitled"}</TableCell>
          <TableCell>
            <div className="flex gap-1">
              {/* Dedup by retailer text (issue #45 follow-up) — two
                  listings on one product can share the same retailer
                  (different URLs, same site; Listing.url is unique but
                  retailer isn't), which would otherwise render two
                  identical badges. */}
              {Array.from(new Set(product.listings.map((listing) => listing.retailer))).map((retailer) => (
                <Badge key={retailer} variant="outline">
                  {retailer}
                </Badge>
              ))}
            </div>
          </TableCell>
          <TableCell>
            {product.status === "processing" ? (
              <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-label="Processing" />
            ) : best !== null ? (
              fmtPrice(best, product.currency)
            ) : (
              "—"
            )}
          </TableCell>
          <TableCell>{fmtPrice(product.target_price, product.currency)}</TableCell>
          <TableCell>
            <Badge variant={status.variant}>{status.label}</Badge>
          </TableCell>
          <TableCell>{product.status === "processing" ? "" : formatLastChecked(product.last_checked)}</TableCell>
          <TableCell>{product.status !== "processing" && <PriceSparkline data={sparklineData} width={80} height={32} />}</TableCell>
          <TableCell onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="ghost" size="icon" aria-label="Item actions">
                    <MoreVertical size={16} strokeWidth={1.25} />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setOpenId(product.id)}>Edit</DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onClick={() => setIsDeleteDialogOpen(true)}>
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </TableCell>
        </TableRow>

        {/* side panel content */}
        <SheetContent side="right" showCloseButton={false}>
          <SheetHeader>
            <div className="flex items-baseline justify-between gap-2">
              {isEditingName ? (
                <div className="min-w-0 flex-1">
                  <SheetTitle className="sr-only">{draft.name || "Untitled"}</SheetTitle>
                  <Input
                    autoFocus
                    value={draft.name}
                    onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                    onBlur={() => setIsEditingName(false)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === "Escape") setIsEditingName(false);
                    }}
                    className="h-7 font-heading text-base font-medium md:text-base"
                  />
                </div>
              ) : (
                <SheetTitle className="[text-box-trim:none]">{draft.name || "Untitled"}</SheetTitle>
              )}
              <Button variant="ghost" size="icon-sm" aria-label="Edit item" className="translate-y-0.5" onClick={() => setIsEditingName(true)}>
                <Pencil size={16} strokeWidth={1.5} />
              </Button>
            </div>
          </SheetHeader>
          <div className="flex flex-col gap-4 px-4">
            <div style={{ height: 200 }}>
              {chartReady && <ProductPriceChart listings={chartListings} targetPrice={product.target_price} currency={product.currency} />}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Target Price</span>
              <div className="flex flex-col items-end gap-0.5">
                {isEditingTargetPrice ? (
                  <InputGroup className="h-7 w-28">
                    <InputGroupAddon>
                      <InputGroupText>{product.currency === "KRW" ? "₩" : "$"}</InputGroupText>
                    </InputGroupAddon>
                    <InputGroupInput
                      autoFocus
                      type="number"
                      step="0.01"
                      value={draft.target_price}
                      onChange={(e) => setDraft((d) => ({ ...d, target_price: e.target.value }))}
                      onBlur={() => setIsEditingTargetPrice(false)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === "Escape") setIsEditingTargetPrice(false);
                      }}
                      className="text-right [appearance:textfield] md:text-sm [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    />
                  </InputGroup>
                ) : (
                  <div className="flex items-center gap-1">
                    <div>
                      <span>{fmtPrice(parseValidPrice(draft.target_price) ?? product.target_price, product.currency)}</span>
                      {(() => {
                        const cadEquivalent = fmtCadEquivalent(product.target_price, product.currency, fxRates);
                        return (
                          cadEquivalent && (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              {cadEquivalent}
                              {fxStale && <StaleFxIcon />}
                            </span>
                          )
                        );
                      })()}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground"
                      aria-label="Edit target price"
                      onClick={() => setIsEditingTargetPrice(true)}
                    >
                      <Pencil className="size-3.5" strokeWidth={1.5} />
                    </Button>
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <div className="flex items-center gap-2">
                <Badge variant={sheetStatus.variant}>{sheetStatus.label}</Badge>
                <Switch
                  checked={draft.active}
                  disabled={product.status === "processing"}
                  aria-label={draft.active ? "Pause item" : "Resume item"}
                  onCheckedChange={(active) => setDraft((d) => ({ ...d, active }))}
                />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground">Retailers</span>
                <div className="flex items-center">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground"
                    aria-label={`Rescrape ${product.name ?? "item"}`}
                    disabled={isPolling || product.status === "processing"}
                    onClick={handleRescrapeProduct}
                  >
                    {isPolling || product.status === "processing" ? (
                      <LoaderCircle size={16} strokeWidth={1.5} className="animate-spin" />
                    ) : (
                      <RefreshCw size={16} strokeWidth={1.5} />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground"
                    aria-label="Add retailer"
                    onClick={() => dispatchEdit({ type: "addListing" })}
                  >
                    <Plus size={16} strokeWidth={1.5} />
                  </Button>
                </div>
              </div>
              {product.listings.map((listing) =>
                editState.type === "listing" && editState.id === listing.id ? (
                  <div key={listing.id} className="flex min-h-14 items-center gap-2 rounded-lg border border-border py-2 px-3">
                    <Input
                      autoFocus
                      type="url"
                      placeholder="https://retailer.com/product"
                      value={editState.draft}
                      onChange={(e) => dispatchEdit({ type: "setDraft", draft: e.target.value })}
                      onBlur={() => dispatchEdit({ type: "cancel" })}
                      onKeyDown={async (e) => {
                        if (e.key === "Enter" && isValidUrl(editState.draft)) {
                          const url = editState.draft;
                          dispatchEdit({ type: "cancel" });
                          if (url === listing.url) return;
                          try {
                            await updateListing(product.id, listing.id, { url });
                            await mutate("/api/proxy/items");
                            setHasRetailerActivity(true);
                            toast.success("Updated");
                          } catch (err) {
                            if (err instanceof ApiError && err.status === 409) {
                              toast.error("That URL is already being watched");
                            } else {
                              toast.error(err instanceof ApiError ? err.detail : "Failed to update listing");
                            }
                          }
                        }
                        if (e.key === "Escape") dispatchEdit({ type: "cancel" });
                      }}
                      className="h-7 flex-1 md:text-sm"
                    />
                  </div>
                ) : (
                  <div key={listing.id} className="flex min-h-14 items-center justify-between rounded-lg border border-border py-2 px-3">
                    <div className="flex items-center gap-2">
                      <span>{listing.retailer}</span>
                      <a
                        href={listing.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Open ${listing.retailer} listing`}
                        className="-mr-1 inline-flex items-center justify-center rounded-md p-1 text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        <ExternalLink size={14} strokeWidth={1.5} />
                      </a>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Stacked, not inline (issue #45 follow-up) — the
                          sheet panel has a fixed max-width, and native
                          price + CAD-equivalent + stale icon + 2 edit
                          buttons all fighting for one line wraps badly on
                          a longer KRW figure. */}
                      <div className="flex flex-col items-end">
                        <span>{listing.last_price !== null ? fmtPrice(listing.last_price, product.currency) : "—"}</span>
                        {listing.last_price !== null &&
                          (() => {
                            const cadEquivalent = fmtCadEquivalent(listing.last_price, product.currency, fxRates);
                            return (
                              cadEquivalent && (
                                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                                  {cadEquivalent}
                                  {fxStale && <StaleFxIcon />}
                                </span>
                              )
                            );
                          })()}
                      </div>
                      <div className="flex items-center">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-muted-foreground"
                          aria-label={`Edit ${listing.retailer} URL`}
                          onClick={() => dispatchEdit({ type: "editListing", id: listing.id, url: listing.url })}
                        >
                          <Pencil className="size-3.5" strokeWidth={1.5} />
                        </Button>
                        {product.listings.length > 1 && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-muted-foreground"
                            aria-label={`Remove ${listing.retailer}`}
                            onClick={async () => {
                              try {
                                await deleteListing(product.id, listing.id);
                                await mutate("/api/proxy/items");
                                setHasRetailerActivity(true);
                                toast.success("Retailer removed");
                              } catch (err) {
                                toast.error(err instanceof ApiError ? err.detail : "Failed to remove retailer");
                              }
                            }}
                          >
                            <Trash2 className="size-3.5" strokeWidth={1.5} />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ),
              )}

              {editState.type === "addingListing" && (
                // min-h-14 — matches the existing retailer rows' height
                // (issue #45 follow-up, same fix as the URL-edit and
                // target_price rows), so this new-listing row doesn't
                // appear a different size than the rows already above it.
                <div className="flex min-h-14 items-center gap-2 rounded-lg border border-border py-2 px-3">
                  <Input
                    autoFocus
                    type="url"
                    placeholder="https://retailer.com/product"
                    value={editState.draft}
                    onChange={(e) => dispatchEdit({ type: "setDraft", draft: e.target.value })}
                    onBlur={() => dispatchEdit({ type: "cancel" })}
                    onKeyDown={async (e) => {
                      if (e.key === "Enter" && isValidUrl(editState.draft)) {
                        const url = editState.draft;
                        dispatchEdit({ type: "cancel" });
                        try {
                          await createListing(product.id, { url });
                          await mutate("/api/proxy/items");
                          setHasRetailerActivity(true);
                          toast.success("Retailer added");
                        } catch (err) {
                          toast.error(err instanceof ApiError ? err.detail : "Failed to add retailer");
                        }
                      }
                      if (e.key === "Escape") dispatchEdit({ type: "cancel" });
                    }}
                    className="h-7 flex-1 md:text-sm"
                  />
                </div>
              )}
            </div>
          </div>
          {/* Governs only name/target_price/active (issue #45 follow-up)
              — retailer add/edit/delete above stays immediate/separate,
              same carve-out market/[ticker]/page.tsx's alert sheet makes
              for Delete. */}
          <SheetFooter className="flex-row justify-end gap-2">
            <Button variant="outline" className="w-20" onClick={handleCancelEdits}>
              Cancel
            </Button>
            <Button className="w-20" onClick={handleSaveEdits} disabled={!dirty || isSaving}>
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete &quot;{product.name ?? "Untitled"}&quot;?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">This removes all retailer listings and their price history.</p>
          <DialogFooter>
            <Button variant="outline" className="w-20" onClick={() => setIsDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" className="w-20" onClick={handleDeleteProduct}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function WatchlistPage() {
  const navSlotEl = useNavSlot();
  const [search, setSearch] = useState("");
  const [searchExpanded, setSearchExpanded] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [chartReady, setChartReady] = useState(false);
  const [editState, dispatchEdit] = useReducer(sheetEditReducer, { type: "none" });
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [newItem, setNewItem] = useState(emptyNewItem);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Issue #51 — same click-to-response-gap coverage as ProductRow's
  // isPolling above; the actual "processing" rows are driven by the
  // existing SSE flow once poll_prices's background task picks them up.
  const [isRescrapingAll, setIsRescrapingAll] = useState(false);

  const handleRescrapeAll = async () => {
    setIsRescrapingAll(true);
    try {
      await pollAllPrices();
      toast.success("Rescraping…");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to trigger rescrape");
    } finally {
      setIsRescrapingAll(false);
    }
  };

  const handleExpandSearch = () => {
    setSearchExpanded(true);
    requestAnimationFrame(() => searchInputRef.current?.focus());
  };

  const handleSearchBlur = () => {
    setTimeout(() => {
      if (!search) setSearchExpanded(false);
    }, 150);
  };

  const resetNewItemForm = () => setNewItem(emptyNewItem);

  const closeAddDialog = () => {
    setIsAddDialogOpen(false);
    resetNewItemForm();
  };

  const newItemUrlLines = newItem.urls
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  // name is optional now (issue #44) — left blank, Product.name stays NULL
  // until the first successful scrape infers it. Not required to submit.
  const canSubmitNewItem = Number(newItem.targetPrice) > 0 && newItemUrlLines.length > 0 && newItemUrlLines.every(isValidUrl);

  // Bulk, single request — backend probes every URL's retailer/scraper_type
  // concurrently (bounded), so this doesn't need the chained-per-URL or
  // background-loop handling earlier revisions of this issue built (see
  // .plan/10.2-wishlist-mutations/implementation.md step 7's design-history
  // note) — a plain awaited call with a button spinner is enough.
  const handleAddItem = async () => {
    if (!canSubmitNewItem || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const trimmedName = newItem.name.trim();
      const { product, failed } = await createProduct({
        // Omitted (not sent as "") when blank — the backend also treats an
        // explicit "" as "not provided", but the frontend form shouldn't
        // rely on that backend leniency when it's this cheap to just not
        // send the key at all.
        name: trimmedName || undefined,
        target_price: Number(newItem.targetPrice),
        urls: newItemUrlLines,
      });
      await mutate("/api/proxy/items");
      closeAddDialog();
      // product.name may still be null here — inference runs async on the
      // first scrape (#41's dispatch), not before this response returns.
      const displayName = product.name ?? "item";
      if (failed.length === 0) {
        toast.success(`Added "${displayName}"`);
      } else {
        const detail = failed.map((f) => `${f.retailer} (${f.detail})`).join(", ");
        toast.error(`"${displayName}": ${failed.length} of ${newItemUrlLines.length} URL(s) failed — ${detail}`, { persist: true });
      }
    } catch (e) {
      // Nothing committed server-side in this case (createProduct itself
      // failed, e.g. 422 on name/target_price) — dialog stays open so the
      // user can fix and retry inline, unlike a partial-failure above where
      // the product already exists and closing is correct.
      toast.error(e instanceof ApiError ? e.detail : "Failed to add item");
    } finally {
      setIsSubmitting(false);
    }
  };

  useEffect(() => {
    if (openId === null) {
      setChartReady(false);
      dispatchEdit({ type: "cancel" });
      return;
    }
    // Delay mounting the chart until the sheet's own open animation has
    // settled — mounting it mid-animation lets Recharts' resize-driven
    // hover recompute fire under a stationary cursor, showing a phantom
    // tooltip with no real mouse-move involved.
    const timer = setTimeout(() => setChartReady(true), 250);
    return () => clearTimeout(timer);
  }, [openId]);

  // Local to every tab regardless of leader/follower role — the browser
  // knows its own network state directly, no relay needed.
  const [isOnline, setIsOnline] = useState(true);
  useEffect(() => {
    const updateOnline = () => setIsOnline(navigator.onLine);
    updateOnline();
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
    };
  }, []);

  // Leader/follower role is decided inside subscribeToListingEvents itself
  // (sse-leader.ts) — this effect looks identical regardless of which one
  // this tab ends up being.
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("online");
  useEffect(() => {
    const unsubscribe = subscribeToListingEvents({
      onEvent: ({ product_id, listing_id }) => {
        mutate("/api/proxy/items");
        mutate(listingHistoryKey(product_id, listing_id));
      },
      onStatusChange: (status) => {
        setConnectionStatus(status);
        // Safety-net refetch on every connect/reconnect, not just per-event —
        // closes the "connected but stale" gap from no Last-Event-ID replay
        // (challenges.md), and this same path is what a newly-promoted
        // leader's fresh connection benefits from too (§6) — no special
        // casing needed, "online" fires the same way either way.
        if (status === "online") mutate("/api/proxy/items");
      },
    });
    return unsubscribe;
  }, []);

  const { data, error, isLoading } = useSWR<Product[]>("/api/proxy/items", fetcher);
  const products = data ?? [];

  // Issue #45 — fetched once on load (SWR's default revalidate-on-focus is
  // harmless here, rates only change daily server-side). getFxRates()
  // gives typed ApiError handling, unlike the raw fetcher() used for
  // products above; {} before the first successful refresh_fx_rates run
  // is a normal response shape (schema.md), not an error — toCad()/
  // fmtCadEquivalent() already treat a missing rate as "nothing to show."
  const { data: fxRatesData } = useSWR<FxRates>("/api/proxy/fx-rates", () => getFxRates());
  const fxRates = fxRatesData?.rates ?? {};
  const fxStale = fxRatesData?.stale ?? false;

  const filtered = products
    .filter((product) => (product.name ?? "").toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

  // FX-converted to CAD before summing (issue #45) — products can be
  // mixed-currency, so a raw sum would add e.g. a KRW price and a USD
  // price as if they were the same unit. A product whose best price is
  // null (no available listing) or whose currency can't yet be converted
  // (missing rate) contributes 0, same "don't let one product poison the
  // total" contract as the pre-#45 `?? 0`.
  const totalBestPrice = products.reduce((sum, product) => {
    const best = bestPrice(product);
    const cadBest = best === null ? null : toCad(best, product.currency, fxRates);
    return sum + (cadBest ?? 0);
  }, 0);

  const triggeredCount = products.filter((product) => product.status === "triggered").length;
  const watchingCount = products.filter((product) => product.status === "watching").length;
  const failedCount = products.filter((product) => product.status === "failed").length;
  // Issue #51 follow-up — drives the global rescrape button's spinner past
  // the click-to-response gap (isRescrapingAll alone) for the actual scrape
  // duration too, same reasoning as ProductRow's own isPolling/status
  // combo below. Broader than "this click's own scrape" (also true during
  // any other in-flight scrape, e.g. #41's add-time first-scrape) — read
  // as "something's actively scraping right now," which is accurate either
  // way and needs no extra per-request tracking to compute.
  const isAnyProcessing = products.some((product) => product.status === "processing");

  if (isLoading) {
    return <LoadingScreen page="Watchlist" />;
  }

  if (error) {
    return (
      <main className="p-5">
        <p className="text-destructive">Failed to load watchlist. Try refreshing.</p>
      </main>
    );
  }

  return (
    <>
      {navSlotEl &&
        createPortal(
          <>
            <div
              className={cn(
                "flex h-8 items-center overflow-hidden rounded-lg border transition-[width,background-color,border-color] duration-300 ease-in-out",
                searchExpanded ? "w-[220px] border-input/30 bg-input/30" : "w-8 border-transparent bg-transparent",
              )}
            >
              <button
                type="button"
                aria-label="Open watchlist search"
                className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
                onClick={handleExpandSearch}
                tabIndex={searchExpanded ? -1 : 0}
              >
                <Search className="size-4 shrink-0 opacity-50" />
              </button>
              <input
                ref={searchInputRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onFocus={() => setSearchExpanded(true)}
                onBlur={handleSearchBlur}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSearch("");
                    setSearchExpanded(false);
                    searchInputRef.current?.blur();
                  }
                }}
                placeholder="Search watchlist..."
                aria-label="Search watchlist"
                className={cn(
                  "h-full min-w-0 bg-transparent text-sm outline-hidden transition-opacity duration-200 disabled:cursor-not-allowed disabled:opacity-50",
                  searchExpanded ? "w-full pr-2 opacity-100 delay-100" : "w-0 opacity-0",
                )}
              />
            </div>
            <button
              type="button"
              aria-label="Rescrape all"
              disabled={isRescrapingAll || isAnyProcessing}
              className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              onClick={handleRescrapeAll}
            >
              {isRescrapingAll || isAnyProcessing ? (
                <LoaderCircle className="size-4 shrink-0 animate-spin opacity-50" />
              ) : (
                <RefreshCw className="size-4 shrink-0 opacity-50" />
              )}
            </button>
            <button
              type="button"
              aria-label="New item"
              className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
              onClick={() => setIsAddDialogOpen(true)}
            >
              <Plus className="size-4 shrink-0 opacity-50" />
            </button>
          </>,
          navSlotEl,
        )}
      <main className="p-5 gap-10 flex flex-col">
        {(!isOnline || connectionStatus === "unavailable") && (
          <Badge variant="outline" className="w-fit text-muted-foreground">
            {!isOnline ? "Offline — will reconnect automatically" : "Live updates unavailable — reconnecting…"}
          </Badge>
        )}
        {/* Overview Left Section */}
        <div className="flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <Label className="font-ndot text-[40px] font-normal block">{fmtValue(totalBestPrice)}</Label>
            {/* "(CAD)" suffix (issue #45, challenges.md #5) — the total is
                always FX-converted to CAD while individual rows stay
                native-currency, so without this it doesn't visually "add
                up" to the rows for a mixed-currency list; this makes that
                deliberate, not a bug. */}
            <Label className="font-ndot text-[20px] font-normal block">Total</Label>
            {fxStale && (
              <span className="self-center">
                <StaleFxIcon />
              </span>
            )}
          </div>
          <div className="flex items-baseline gap-20 pr-20">
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{products.length}</Label>
              <Label className="text-muted-foreground">Items</Label>
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{triggeredCount}</Label>
              <Label className="text-muted-foreground">Triggered</Label>
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{watchingCount}</Label>
              <Label className="text-muted-foreground">Watching</Label>
            </div>
            {failedCount > 0 && (
              <div className="flex flex-col gap-1">
                <Label className="text-md font-ndot" style={{ color: "var(--status-error)" }}>
                  {failedCount}
                </Label>
                <Label className="text-muted-foreground">Failed</Label>
              </div>
            )}
          </div>
        </div>
        <Dialog open={isAddDialogOpen} onOpenChange={(open) => (open ? setIsAddDialogOpen(true) : closeAddDialog())}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Item</DialogTitle>
            </DialogHeader>
            <div className="flex min-w-0 flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-item-name">Item Name</Label>
                <Input id="new-item-name" value={newItem.name} onChange={(e) => setNewItem((prev) => ({ ...prev, name: e.target.value }))} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-item-target-price">Target Price</Label>
                <Input
                  id="new-item-target-price"
                  type="number"
                  step="0.01"
                  value={newItem.targetPrice}
                  onChange={(e) => setNewItem((prev) => ({ ...prev, targetPrice: e.target.value }))}
                  className="[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="new-item-urls">Retailer URLs</Label>
                <Textarea
                  id="new-item-urls"
                  rows={4}
                  value={newItem.urls}
                  onChange={(e) => setNewItem((prev) => ({ ...prev, urls: e.target.value }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" className="w-20" onClick={closeAddDialog}>
                Cancel
              </Button>
              <Button className="w-20" disabled={!canSubmitNewItem || isSubmitting} onClick={handleAddItem}>
                {isSubmitting ? "Saving…" : "Save"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <Card className="w-full p-0">
          <Table>
            <TableHeader className="[&_th]:h-auto [&_th]:px-4 [&_th]:pt-4 [&_th]:pb-4">
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Retailer</TableHead>
                <TableHead>Best Price</TableHead>
                <TableHead>Target Price</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Checked</TableHead>
                <TableHead>Price History</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody className="[&_td]:px-4 [&_td]:py-4">
              {filtered.length === 0 ? (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    No items yet.
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((product) => (
                  <ProductRow
                    key={product.id}
                    product={product}
                    openId={openId}
                    setOpenId={setOpenId}
                    fxRates={fxRates}
                    fxStale={fxStale}
                    editState={editState}
                    dispatchEdit={dispatchEdit}
                    chartReady={chartReady}
                  />
                ))
              )}
            </TableBody>
          </Table>
        </Card>
      </main>
    </>
  );
}
