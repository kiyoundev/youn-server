"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PriceSparkline } from "@/components/ui/price-sparkline";
import { ProductPriceChart } from "@/components/ui/product-price-chart";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ExternalLink, MoreVertical, Plus, Search, Pencil, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useNavSlot } from "@/components/nav-slot";

type WatchStatus = "watching" | "triggered" | "paused" | "failed";

interface Listing {
  id: string;
  retailer: string;
  url: string;
  price: number;
  lastCheckedAt: string;
  priceHistory: { date: string; price: number }[];
}

interface Product {
  id: string;
  name: string;
  targetPrice: number;
  status: WatchStatus;
  listings: Listing[];
  createdAt: string;
}

const products: Product[] = [
  {
    id: "airpods-max-2",
    name: "Apple AirPods Max 2",
    targetPrice: 500,
    status: "watching",
    createdAt: "2026-07-10T09:00:00Z",
    listings: [
      {
        id: "l1",
        retailer: "Costco",
        url: "https://www.costco.ca/apple-airpods-max-2.product",
        price: 520,
        lastCheckedAt: "2026-07-25T02:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 560 },
          { date: "2026-07-08", price: 545 },
          { date: "2026-07-15", price: 530 },
          { date: "2026-07-22", price: 520 },
        ],
      },
      {
        id: "l2",
        retailer: "BestBuy",
        url: "https://www.bestbuy.ca/apple-airpods-max-2.product",
        price: 549.99,
        lastCheckedAt: "2026-07-25T02:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 579.99 },
          { date: "2026-07-08", price: 569.99 },
          { date: "2026-07-15", price: 559.99 },
          { date: "2026-07-22", price: 549.99 },
        ],
      },
    ],
  },
  {
    id: "switch-2",
    name: "Nintendo Switch 2",
    targetPrice: 450,
    status: "triggered",
    createdAt: "2026-07-20T14:30:00Z",
    listings: [
      {
        id: "l3",
        retailer: "BestBuy",
        url: "https://www.bestbuy.ca/nintendo-switch-2.product",
        price: 429.99,
        lastCheckedAt: "2026-07-25T08:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 459.99 },
          { date: "2026-07-08", price: 459.99 },
          { date: "2026-07-15", price: 449.99 },
          { date: "2026-07-22", price: 429.99 },
        ],
      },
      {
        id: "l4",
        retailer: "Walmart",
        url: "https://www.walmart.ca/nintendo-switch-2.product",
        price: 439.99,
        lastCheckedAt: "2026-07-25T08:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 449.99 },
          { date: "2026-07-08", price: 449.99 },
          { date: "2026-07-15", price: 439.99 },
          { date: "2026-07-22", price: 439.99 },
        ],
      },
    ],
  },
  {
    id: "uniqlo-shorts",
    name: "Uniqlo Geared Shorts",
    targetPrice: 30,
    status: "paused",
    createdAt: "2026-07-05T11:15:00Z",
    listings: [
      {
        id: "l5",
        retailer: "Uniqlo",
        url: "https://www.uniqlo.com/ca/en/geared-shorts.product",
        price: 39.9,
        lastCheckedAt: "2026-07-18T02:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 34.9 },
          { date: "2026-07-08", price: 36.9 },
          { date: "2026-07-15", price: 39.9 },
          { date: "2026-07-18", price: 39.9 },
        ],
      },
    ],
  },
  {
    id: "sony-xm6",
    name: "Sony WH-1000XM6",
    targetPrice: 350,
    status: "failed",
    createdAt: "2026-06-28T08:00:00Z",
    listings: [
      {
        id: "l6",
        retailer: "Amazon",
        url: "https://www.amazon.ca/sony-wh-1000xm6.product",
        price: 398,
        lastCheckedAt: "2026-07-25T02:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 369.99 },
          { date: "2026-07-08", price: 375.0 },
          { date: "2026-07-15", price: 385.0 },
          { date: "2026-07-22", price: 398.0 },
        ],
      },
      {
        id: "l7",
        retailer: "BestBuy",
        url: "https://www.bestbuy.ca/sony-wh-1000xm6.product",
        price: 379.99,
        lastCheckedAt: "2026-07-19T14:00:00Z",
        priceHistory: [
          { date: "2026-07-01", price: 360.0 },
          { date: "2026-07-08", price: 365.0 },
          { date: "2026-07-15", price: 370.0 },
          { date: "2026-07-22", price: 379.99 },
        ],
      },
    ],
  },
];

const bestPrice = (product: Product) => Math.min(...product.listings.map((l) => l.price));

const stalestCheckedAt = (product: Product) =>
  product.listings.reduce((oldest, l) => (new Date(l.lastCheckedAt) < new Date(oldest.lastCheckedAt) ? l : oldest)).lastCheckedAt;

const productPriceHistory = (product: Product) => {
  const dates = Array.from(new Set(product.listings.flatMap((l) => l.priceHistory.map((h) => h.date)))).sort();

  return dates.map((date) => {
    const pricesOnDate = product.listings
      .map((l) => l.priceHistory.find((h) => h.date === date)?.price)
      .filter((price): price is number => price !== undefined);
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
};

const formatLastChecked = (iso: string) => {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
};

function fmtValue(value: number) {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

const emptyNewItem = { name: "", targetPrice: "", urls: "" };

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
  | { type: "listing"; id: string; draft: string }
  | { type: "addingListing"; draft: string };

type SheetEditAction =
  | { type: "editName"; name: string }
  | { type: "editTargetPrice"; targetPrice: number }
  | { type: "editListing"; id: string; url: string }
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

export default function WatchlistPage() {
  const navSlotEl = useNavSlot();
  const [search, setSearch] = useState("");
  const [searchExpanded, setSearchExpanded] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [chartReady, setChartReady] = useState(false);
  const [editState, dispatchEdit] = useReducer(sheetEditReducer, { type: "none" });
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [newItem, setNewItem] = useState(emptyNewItem);

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

  const filtered = products
    .filter((product) => product.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());

  const totalBestPrice = products.reduce((sum, product) => sum + bestPrice(product), 0);

  const triggeredCount = products.filter((product) => product.status === "triggered").length;
  const watchingCount = products.filter((product) => product.status === "watching").length;
  const failedCount = products.filter((product) => product.status === "failed").length;

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
        {/* Overview Left Section */}
        <div className="flex justify-between">
          <div className="flex items-baseline gap-2">
            <Label className="font-ndot text-[40px] font-normal block">{fmtValue(totalBestPrice)}</Label>
            <Label className="font-ndot text-[20px] font-normal block">Total</Label>
          </div>
          <div className="flex gap-20 pr-20">
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
            <div className="flex flex-col gap-4">
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
              <div className="flex flex-col gap-1.5">
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
              <Button
                className="w-20"
                disabled={!canSubmitNewItem}
                onClick={() => {
                  console.log("add new item", {
                    name: newItem.name,
                    targetPrice: Number(newItem.targetPrice),
                    urls: newItemUrlLines,
                  });
                  closeAddDialog();
                }}
              >
                Save
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
              {filtered.map((product) => {
                const status = STATUS_BADGE[product.status];
                return (
                  <Sheet key={product.id} open={openId === product.id} onOpenChange={(open) => setOpenId(open ? product.id : null)}>
                    <SheetTrigger render={<TableRow className="cursor-pointer" />}>
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
                      <TableCell>${bestPrice(product).toFixed(2)}</TableCell>
                      <TableCell>${product.targetPrice.toFixed(2)}</TableCell>
                      <TableCell>
                        <Badge variant={status.variant}>{status.label}</Badge>
                      </TableCell>
                      <TableCell>{formatLastChecked(stalestCheckedAt(product))}</TableCell>
                      <TableCell>
                        <PriceSparkline data={productPriceHistory(product)} width={80} height={32} />
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
                            <DropdownMenuItem variant="destructive" onClick={() => console.log("delete", product.id)}>
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </SheetTrigger>

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
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    console.log("save name", product.id, editState.draft);
                                    dispatchEdit({ type: "cancel" });
                                  }
                                  if (e.key === "Escape") dispatchEdit({ type: "cancel" });
                                }}
                                className="h-7 font-heading text-base font-medium md:text-base"
                              />
                            </div>
                          ) : (
                            <SheetTitle>{product.name}</SheetTitle>
                          )}
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="Edit item"
                            onClick={() => dispatchEdit({ type: "editName", name: product.name })}
                          >
                            <Pencil size={16} strokeWidth={1.5} />
                          </Button>
                        </div>
                      </SheetHeader>
                      <div className="flex flex-col gap-4 px-4">
                        <div style={{ height: 200 }}>
                          {chartReady && <ProductPriceChart listings={product.listings} targetPrice={product.targetPrice} />}
                        </div>
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
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  console.log("save target price", product.id, editState.draft);
                                  dispatchEdit({ type: "cancel" });
                                }
                                if (e.key === "Escape") dispatchEdit({ type: "cancel" });
                              }}
                              className="h-7 w-24 text-right [appearance:textfield] md:text-sm [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                            />
                          ) : (
                            <div className="flex items-center gap-1">
                              <span>${product.targetPrice.toFixed(2)}</span>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                className="text-muted-foreground"
                                aria-label="Edit target price"
                                onClick={() => dispatchEdit({ type: "editTargetPrice", targetPrice: product.targetPrice })}
                              >
                                <Pencil className="size-3.5" strokeWidth={1.5} />
                              </Button>
                            </div>
                          )}
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">Status</span>
                          <Badge variant={status.variant}>{status.label}</Badge>
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
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter" && isValidUrl(editState.draft)) {
                                      console.log("save listing url", product.id, listing.id, editState.draft);
                                      dispatchEdit({ type: "cancel" });
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
                                  <span>${listing.price.toFixed(2)}</span>
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
                                    <Button
                                      variant="ghost"
                                      size="icon-sm"
                                      className="text-muted-foreground"
                                      aria-label={`Remove ${listing.retailer}`}
                                      disabled={product.listings.length <= 1}
                                      onClick={() => console.log("remove listing", product.id, listing.id)}
                                    >
                                      <Trash2 className="size-3.5" strokeWidth={1.5} />
                                    </Button>
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
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" && isValidUrl(editState.draft)) {
                                    console.log("add listing", product.id, editState.draft);
                                    dispatchEdit({ type: "cancel" });
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
                );
              })}
            </TableBody>
          </Table>
        </Card>
      </main>
    </>
  );
}
