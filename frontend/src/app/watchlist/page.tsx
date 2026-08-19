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
import { ExternalLink, LoaderCircle, MoreVertical, Plus, Search, Pencil, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { LoadingScreen } from "@/components/ui/loading-screen";
import { cn } from "@/lib/utils";
import { useNavSlot } from "@/components/nav-slot";
import { useListingHistory, bucketByLocalDay, listingHistoryKey } from "@/lib/hooks/use-listing-history";
import { subscribeToListingEvents, type ConnectionStatus } from "@/lib/sse-leader";
import {
  createProduct,
  createListing,
  updateProduct,
  updateListing,
  deleteListing,
  deleteProduct,
  ApiError,
  type Product,
  type Listing,
  type WatchStatus,
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

// Which single field in the currently-open sheet is being edited, if any —
// modeled as one state so switching modes always replaces the whole thing
// rather than relying on every handler to reset every other flag by hand.
type SheetEditState =
  | { type: "none" }
  | { type: "name"; draft: string }
  | { type: "targetPrice"; draft: string }
  | { type: "listing"; id: number; draft: string }
  | { type: "addingListing"; draft: string };

type SheetEditAction =
  | { type: "editName"; name: string }
  | { type: "editTargetPrice"; targetPrice: number }
  | { type: "editListing"; id: number; url: string }
  | { type: "addListing" }
  | { type: "setDraft"; draft: string }
  | { type: "cancel" };

function sheetEditReducer(state: SheetEditState, action: SheetEditAction): SheetEditState {
  switch (action.type) {
    case "editName":
      return { type: "name", draft: action.name };
    case "editTargetPrice":
      return { type: "targetPrice", draft: String(action.targetPrice) };
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
}: {
  product: Product;
  openId: number | null;
  setOpenId: (id: number | null) => void;
  editState: SheetEditState;
  dispatchEdit: (action: SheetEditAction) => void;
  chartReady: boolean;
}) {
  // Mounted unconditionally with the row (not gated by the sheet being
  // open), so history is already warm by the time this row's sheet opens —
  // the only way to reach it is through this row, so it's already mounted.
  const [historyByListing, setHistoryByListing] = useState<Record<number, HistoryPoint[]>>({});
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);

  const handleHistoryData = useCallback((listingId: number, points: HistoryPoint[]) => {
    setHistoryByListing((prev) => ({ ...prev, [listingId]: points }));
  }, []);

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

  const status = STATUS_BADGE[product.status];
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
          <TableCell className="font-medium">{product.name}</TableCell>
          <TableCell>
            <div className="flex gap-1">
              {product.listings.map((listing) => (
                <Badge key={listing.id} variant="outline">
                  {listing.retailer}
                </Badge>
              ))}
            </div>
          </TableCell>
          <TableCell>
            {product.status === "processing" ? (
              <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-label="Processing" />
            ) : best !== null ? (
              `$${best.toFixed(2)}`
            ) : (
              "—"
            )}
          </TableCell>
          <TableCell>${product.target_price.toFixed(2)}</TableCell>
          <TableCell>
            <Badge variant={status.variant}>{status.label}</Badge>
          </TableCell>
          <TableCell>{product.status === "processing" ? "" : formatLastChecked(product.last_checked)}</TableCell>
          <TableCell>
            {product.status !== "processing" && <PriceSparkline data={sparklineData} width={80} height={32} />}
          </TableCell>
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
        <SheetContent side="right">
          <SheetHeader>
            <div className="flex items-center gap-2 pr-10">
              {editState.type === "name" ? (
                <div className="min-w-0 flex-1">
                  <SheetTitle className="sr-only">{product.name}</SheetTitle>
                  <Input
                    autoFocus
                    value={editState.draft}
                    onChange={(e) => dispatchEdit({ type: "setDraft", draft: e.target.value })}
                    onBlur={() => dispatchEdit({ type: "cancel" })}
                    onKeyDown={async (e) => {
                      if (e.key === "Enter") {
                        const name = editState.draft.trim();
                        dispatchEdit({ type: "cancel" });
                        if (!name || name === product.name) return;
                        try {
                          await updateProduct(product.id, { name });
                          await mutate("/api/proxy/items");
                          toast.success("Updated");
                        } catch (err) {
                          toast.error(err instanceof ApiError ? err.detail : "Failed to update name");
                        }
                      }
                      if (e.key === "Escape") dispatchEdit({ type: "cancel" });
                    }}
                    className="h-7 font-heading text-base font-medium md:text-base"
                  />
                </div>
              ) : (
                <SheetTitle>{product.name}</SheetTitle>
              )}
              <Button variant="ghost" size="icon-sm" aria-label="Edit item" onClick={() => dispatchEdit({ type: "editName", name: product.name })}>
                <Pencil size={16} strokeWidth={1.5} />
              </Button>
            </div>
          </SheetHeader>
          <div className="flex flex-col gap-4 px-4">
            <div style={{ height: 200 }}>{chartReady && <ProductPriceChart listings={chartListings} targetPrice={product.target_price} />}</div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Target Price</span>
              {editState.type === "targetPrice" ? (
                <Input
                  autoFocus
                  type="number"
                  step="0.01"
                  value={editState.draft}
                  onChange={(e) => dispatchEdit({ type: "setDraft", draft: e.target.value })}
                  onBlur={() => dispatchEdit({ type: "cancel" })}
                  onKeyDown={async (e) => {
                    if (e.key === "Enter") {
                      const target_price = Number(editState.draft);
                      dispatchEdit({ type: "cancel" });
                      if (!(target_price > 0) || target_price === product.target_price) return;
                      try {
                        await updateProduct(product.id, { target_price });
                        await mutate("/api/proxy/items");
                        toast.success("Updated");
                      } catch (err) {
                        toast.error(err instanceof ApiError ? err.detail : "Failed to update target price");
                      }
                    }
                    if (e.key === "Escape") dispatchEdit({ type: "cancel" });
                  }}
                  className="h-7 w-24 text-right [appearance:textfield] md:text-sm [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />
              ) : (
                <div className="flex items-center gap-1">
                  <span>${product.target_price.toFixed(2)}</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground"
                    aria-label="Edit target price"
                    onClick={() => dispatchEdit({ type: "editTargetPrice", targetPrice: product.target_price })}
                  >
                    <Pencil className="size-3.5" strokeWidth={1.5} />
                  </Button>
                </div>
              )}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <div className="flex items-center gap-2">
                <Badge variant={status.variant}>{status.label}</Badge>
                <Switch
                  checked={product.status !== "paused"}
                  disabled={product.status === "processing"}
                  aria-label={product.status !== "paused" ? "Pause item" : "Resume item"}
                  onCheckedChange={async (active) => {
                    try {
                      await updateProduct(product.id, { active });
                      await mutate("/api/proxy/items");
                      toast.success(active ? "Resumed" : "Paused");
                    } catch (err) {
                      toast.error(err instanceof ApiError ? err.detail : "Failed to update");
                    }
                  }}
                />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground">Retailers</span>
                <Button variant="ghost" size="icon-sm" aria-label="Add retailer" onClick={() => dispatchEdit({ type: "addListing" })}>
                  <Plus size={16} strokeWidth={1.5} />
                </Button>
              </div>
              {product.listings.map((listing) =>
                editState.type === "listing" && editState.id === listing.id ? (
                  <div key={listing.id} className="flex items-center gap-2 rounded-lg border border-border py-2 px-3">
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
                  <div key={listing.id} className="flex items-center justify-between rounded-lg border border-border py-2 px-3">
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
                      <span>{listing.last_price !== null ? `$${listing.last_price.toFixed(2)}` : "—"}</span>
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
                <div className="flex items-center gap-2 rounded-lg border border-border py-2 px-3">
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
        </SheetContent>
      </Sheet>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete &quot;{product.name}&quot;?</DialogTitle>
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

  const canSubmitNewItem =
    newItem.name.trim() !== "" && Number(newItem.targetPrice) > 0 && newItemUrlLines.length > 0 && newItemUrlLines.every(isValidUrl);

  // Bulk, single request — backend probes every URL's retailer/scraper_type
  // concurrently (bounded), so this doesn't need the chained-per-URL or
  // background-loop handling earlier revisions of this issue built (see
  // .plan/10.2-wishlist-mutations/implementation.md step 7's design-history
  // note) — a plain awaited call with a button spinner is enough.
  const handleAddItem = async () => {
    if (!canSubmitNewItem || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const { product, failed } = await createProduct({
        name: newItem.name.trim(),
        target_price: Number(newItem.targetPrice),
        urls: newItemUrlLines,
      });
      await mutate("/api/proxy/items");
      closeAddDialog();
      if (failed.length === 0) {
        toast.success(`Added "${product.name}"`);
      } else {
        const detail = failed.map((f) => `${f.url} (${f.detail})`).join(", ");
        toast.error(`"${product.name}": ${failed.length} of ${newItemUrlLines.length} URL(s) failed — ${detail}`, { persist: true });
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

  const filtered = products
    .filter((product) => product.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

  const totalBestPrice = products.reduce((sum, product) => sum + (bestPrice(product) ?? 0), 0);

  const triggeredCount = products.filter((product) => product.status === "triggered").length;
  const watchingCount = products.filter((product) => product.status === "watching").length;
  const failedCount = products.filter((product) => product.status === "failed").length;

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
            <Label className="font-ndot text-[20px] font-normal block">Total</Label>
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
        <Card className="w-full px-4">
          <Table>
            <TableHeader className="[&_th]:h-auto [&_th]:px-2 [&_th]:pt-0 [&_th]:pb-4">
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
            <TableBody className="[&_td]:py-4 [&_tr:last-child_td]:pb-0">
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
