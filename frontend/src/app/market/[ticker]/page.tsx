"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import useSWR, { mutate } from "swr";
import { POLL_INTERVAL_MS } from "@/lib/polling";
import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { stockWatchlistData } from "@/lib/mock-portfolio";
import { MarketDetailChart, type ChartPoint } from "@/components/ui/market-detail-chart";
import { RecentActivityCard } from "@/components/ui/recent-activity-card";
import { createStockAlert, updateStockAlert, deleteStockAlert, type StockAlert } from "@/lib/api/stock-alerts";
import { ApiError } from "@/lib/api/api-client";
import { toast } from "@/lib/toast";
import {
  DATE_RANGES,
  type Activity,
  type DateRange,
  generateMockPriceSeries,
  getActivitiesForTicker,
  getMarketDetail,
  getPositionForTicker,
  getTotalPortfolioValue,
} from "@/lib/mock-market";
import { AlarmClockPlus, Star, Trash2, TrendingDown, TrendingUp } from "lucide-react";

const NY_TIME_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  hour: "numeric",
  minute: "numeric",
  hourCycle: "h23",
});

function isMarketOpenNow(): boolean {
  const parts = NY_TIME_FORMAT.formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  if (get("weekday") === "Sat" || get("weekday") === "Sun") return false;
  const minutes = Number(get("hour")) * 60 + Number(get("minute"));
  return minutes >= 9 * 60 + 30 && minutes < 16 * 60;
}

function fmtCurrency(value: number, currency: string) {
  return value.toLocaleString("en-US", { style: "currency", currency });
}

function fmtCompact(value: number) {
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 2 });
}

function fmtCompactCurrency(value: number, currency: string) {
  return value.toLocaleString("en-US", { style: "currency", currency, notation: "compact", maximumFractionDigits: 2 });
}

function groupByDate(activities: Activity[]) {
  return activities.reduce<Record<string, Activity[]>>((acc, a) => {
    (acc[a.transactionDate] ??= []).push(a);
    return acc;
  }, {});
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <Label className="text-muted-foreground text-sm">{label}</Label>
      <Label className="text-sm font-normal">{value}</Label>
    </div>
  );
}

// Local draft shape for one section — nothing here ever reaches the network
// on its own; edits/toggles only update this, until the sheet-level Save
// diffs it against the real alert (if any) and fires whatever changed.
// target_price stays a string (controlled Input value) until parsed at save
// time, same reason every other numeric Input in this codebase does this.
type AlertDraft = {
  target_price: string;
  active: boolean;
  run_analysis: boolean;
};

function draftFromAlert(alert?: StockAlert): AlertDraft {
  return {
    target_price: alert ? String(alert.target_price) : "",
    // active can't be sent on create (StockAlertCreate has no such field —
    // new alerts always start active) — default true here purely so the
    // Switch's displayed value matches what creating will actually produce;
    // it stays disabled in that case (see AlertSection) since toggling it
    // pre-creation wouldn't do anything.
    active: alert ? alert.active : true,
    run_analysis: alert ? alert.run_analysis : false,
  };
}

// Parses a draft price field, returning null for anything that isn't a
// finite, positive number — same guard the pre-refactor per-field-commit
// code applied before every mutation (`if (!(target_price > 0)) return;`),
// reinstated here so a bad/empty string can't register as "dirty" and reach
// createStockAlert/updateStockAlert as NaN (which JSON.stringify serializes
// to `null`, surfacing as a generic "Failed to save alert" toast instead of
// being caught client-side).
function parseValidPrice(raw: string): number | null {
  if (raw.trim() === "") return null;
  const price = Number(raw);
  return Number.isFinite(price) && price > 0 ? price : null;
}

function isSectionDirty(alert: StockAlert | undefined, draft: AlertDraft): boolean {
  const price = parseValidPrice(draft.target_price);
  if (!alert) return price !== null;
  return (price !== null && price !== alert.target_price) || draft.active !== alert.active || draft.run_analysis !== alert.run_analysis;
}

// Fires whatever this section's draft actually needs — one updateStockAlert
// call (only the fields that changed) if alert exists, one createStockAlert
// call if it doesn't. Caller (handleSave) only invokes this for dirty
// sections, so "nothing to do" isn't a case this needs to handle. A
// not-yet-valid price never reaches here in that case either — isSectionDirty
// only reports dirty on the create path once parseValidPrice succeeds.
async function saveSection(ticker: string, direction: "above" | "below", alert: StockAlert | undefined, draft: AlertDraft) {
  const price = parseValidPrice(draft.target_price);
  if (alert) {
    const changed: Parameters<typeof updateStockAlert>[1] = {};
    if (price !== null && price !== alert.target_price) changed.target_price = price;
    if (draft.active !== alert.active) changed.active = draft.active;
    if (draft.run_analysis !== alert.run_analysis) changed.run_analysis = draft.run_analysis;
    await updateStockAlert(alert.id, changed);
  } else {
    if (price === null) return;
    await createStockAlert({ ticker, target_price: price, direction, run_analysis: draft.run_analysis });
  }
}

// One section of the alarm Sheet — "above" or "below". Always shows the
// same full field set (price, active, run_analysis) whether a real alert
// exists yet or not — revised 2026-08-13, replaces the earlier
// empty-vs-populated asymmetry (see implementation.md's Step 3 note for
// why). Purely controlled — every edit updates the parent-owned draft,
// nothing here ever calls the API directly. Delete stays immediate/
// separate, gated on a real alert existing (nothing to delete otherwise).
function AlertSection({
  direction,
  alert,
  draft,
  onDraftChange,
  onDeleteRequest,
}: {
  direction: "above" | "below";
  alert?: StockAlert;
  draft: AlertDraft;
  onDraftChange: (draft: AlertDraft) => void;
  onDeleteRequest: (alert: StockAlert) => void;
}) {
  const direction_label = direction === "above" ? "Above Threshold Alert" : "Below Threshold Alert";
  const icon =
    direction === "above" ? <TrendingUp className="h-4 w-4 text-muted-foreground" /> : <TrendingDown className="h-4 w-4 text-muted-foreground" />;

  return (
    <div className="flex flex-col gap-3 border-b pb-4 last:border-b-0">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {icon}
          <Label className="text-sm text-muted-foreground">{direction_label}</Label>
        </div>
        {alert && (
          <Button variant="ghost" size="icon" onClick={() => onDeleteRequest(alert)}>
            <Trash2 className="h-4 w-4 text-muted-foreground" />
          </Button>
        )}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Target price</span>
        <Input
          type="number"
          step="0.01"
          placeholder="Target price"
          value={draft.target_price}
          onChange={(e) => onDraftChange({ ...draft, target_price: e.target.value })}
          className="h-7 w-28 text-right [appearance:textfield] md:text-sm [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Active</span>
        <Switch
          checked={draft.active}
          disabled={!alert}
          aria-label={draft.active ? "Pause alert" : "Resume alert"}
          onCheckedChange={(active) => onDraftChange({ ...draft, active })}
        />
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Run analysis on trigger</span>
        <Switch
          checked={draft.run_analysis}
          aria-label={draft.run_analysis ? "Disable analysis" : "Enable analysis"}
          onCheckedChange={(run_analysis) => onDraftChange({ ...draft, run_analysis })}
        />
      </div>
    </div>
  );
}

export default function MarketDetailPage() {
  // params
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker;

  // states
  const [selectedRange, setSelectedRange] = useState<DateRange>("YTD");
  const [returnWindow, setReturnWindow] = useState<"1D" | "All">("All");
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<ChartPoint | null>(null);
  const [watchlisted, setWatchlisted] = useState(() => stockWatchlistData.some((a) => a.ticker === ticker));
  const [sheetOpen, setSheetOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<StockAlert | null>(null);

  // Same SWR key /portfolio's Watchlist tile would use if it read this
  // endpoint — it doesn't (see #10.6) — but this page and #10.4's dialog-
  // that-became-a-sheet both do, so this is still the one real dedup point
  // for /api/proxy/stockalerts today.
  const alertsFetcher = (url: string) => fetch(url).then((r) => r.json());
  const { data: alerts } = useSWR<StockAlert[]>("/api/proxy/stockalerts", alertsFetcher, { refreshInterval: POLL_INTERVAL_MS });
  const alertsForTicker = alerts?.filter((a) => a.ticker === ticker) ?? [];
  const aboveAlert = alertsForTicker.find((a) => a.direction === "above");
  const belowAlert = alertsForTicker.find((a) => a.direction === "below");
  const hasAlerts = alertsForTicker.length > 0;

  const [aboveDraft, setAboveDraft] = useState<AlertDraft>(() => draftFromAlert(aboveAlert));
  const [belowDraft, setBelowDraft] = useState<AlertDraft>(() => draftFromAlert(belowAlert));
  const [isSaving, setIsSaving] = useState(false);

  // Reset drafts to current server truth only when the sheet opens — not
  // every time the underlying SWR poll refreshes while it's open. A draft
  // session can legitimately outlive the data it started from (see
  // challenges.md item 4); resetting on every revalidation would silently
  // blow away in-progress edits mid-session.
  useEffect(() => {
    if (sheetOpen) {
      setAboveDraft(draftFromAlert(aboveAlert));
      setBelowDraft(draftFromAlert(belowAlert));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheetOpen]);

  const aboveDirty = isSectionDirty(aboveAlert, aboveDraft);
  const belowDirty = isSectionDirty(belowAlert, belowDraft);
  const anyDirty = aboveDirty || belowDirty;

  function handleCancel() {
    setAboveDraft(draftFromAlert(aboveAlert));
    setBelowDraft(draftFromAlert(belowAlert));
    setSheetOpen(false);
  }

  async function handleSave() {
    setIsSaving(true);
    const results = await Promise.allSettled([
      aboveDirty ? saveSection(ticker, "above", aboveAlert, aboveDraft) : Promise.resolve(),
      belowDirty ? saveSection(ticker, "below", belowAlert, belowDraft) : Promise.resolve(),
    ]);
    setIsSaving(false);
    await mutate("/api/proxy/stockalerts");

    const failures = results.filter((r): r is PromiseRejectedResult => r.status === "rejected");
    if (failures.length === 0) {
      toast.success("Alerts saved");
      setSheetOpen(false);
    } else {
      for (const failure of failures) {
        const err = failure.reason;
        if (err instanceof ApiError && err.status === 409) {
          toast.error("An alert for this direction already exists");
        } else {
          toast.error(err instanceof ApiError ? err.detail : "Failed to save alert");
        }
      }
      // Sheet stays open — a partially-successful save (e.g. "above" saved,
      // "below" 409'd) shouldn't hide the section that still needs attention.
    }
  }

  useEffect(() => {
    setMarketOpen(isMarketOpenNow());
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "q" || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      setSelectedRange((prev) => DATE_RANGES[(DATE_RANGES.indexOf(prev) + 1) % DATE_RANGES.length]);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const detail = useMemo(() => getMarketDetail(ticker), [ticker]);
  const position = useMemo(() => getPositionForTicker(ticker), [ticker]);
  const activities = useMemo(() => getActivitiesForTicker(ticker), [ticker]);

  const chartData = useMemo(() => generateMockPriceSeries(ticker, detail.currentPrice, selectedRange), [ticker, detail.currentPrice, selectedRange]);

  const firstPoint = chartData[0]?.value ?? detail.currentPrice;
  const displayedPrice = hoveredPoint?.value ?? detail.currentPrice;
  const changeDollar = displayedPrice - firstPoint;
  const changePercent = firstPoint !== 0 ? (changeDollar / firstPoint) * 100 : 0;
  const isPositive = changeDollar >= 0;
  const changeColor = isPositive ? "var(--status-success)" : "var(--status-error)";

  // Chart's own gain/loss color (for the line + hover split) tracks the range's
  // overall direction, not the currently-hovered point, so it doesn't flicker
  // between colors as the user scrubs across a single up-then-down range.
  const rangeChangeDollar = detail.currentPrice - firstPoint;
  const isRangePositive = rangeChangeDollar >= 0;

  // activities is sorted latest-first — the dashed reference line marks the
  // most recent buy tranche's price, not the position's weighted avg_cost.
  const latestActivity = activities[0];
  const referenceCost = latestActivity?.unitPrice ?? position?.avgPrice;
  const referenceDate = latestActivity?.transactionDate ?? position?.purchasedAt;

  const totalPortfolioValue = getTotalPortfolioValue();
  const positionValue = position ? position.shares * position.currentPrice : 0;
  const allocationPct = position && totalPortfolioValue > 0 ? (positionValue / totalPortfolioValue) * 100 : 0;
  const returnBasisPrice = returnWindow === "1D" ? detail.open : position?.avgPrice;
  const positionGainDollar = position && returnBasisPrice ? (position.currentPrice - returnBasisPrice) * position.shares : 0;
  const positionGainPercent = position && returnBasisPrice ? ((position.currentPrice - returnBasisPrice) / returnBasisPrice) * 100 : 0;
  const positionGainColor = positionGainDollar >= 0 ? "var(--status-success)" : "var(--status-error)";

  const avgCostDate = referenceDate ? [...chartData].reverse().find((d) => d.date <= referenceDate)?.date : undefined;

  const activityGroups = groupByDate(activities);

  return (
    <main className="flex flex-col gap-4 p-5">
      {/* Header */}
      <div className="flex justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 shrink-0 rounded-lg" style={{ backgroundColor: detail.logoColor }} />
          <Label className="text-lg font-medium">{ticker}</Label>
          <Label className="text-muted-foreground">{detail.name}</Label>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={watchlisted ? "Remove from watchlist" : "Add to watchlist"}
            aria-pressed={watchlisted}
            onClick={() => setWatchlisted((prev) => !prev)}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
          >
            <Star className={cn("size-4 shrink-0", watchlisted ? "fill-foreground opacity-100" : "opacity-50")} />
          </button>
          <button
            type="button"
            aria-label={hasAlerts ? "View alerts" : "Add alert"}
            onClick={() => setSheetOpen(true)}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
          >
            <AlarmClockPlus className={cn("size-4 shrink-0", hasAlerts ? "fill-foreground opacity-100" : "opacity-50")} />
          </button>
        </div>
      </div>
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right">
          <SheetHeader>
            <div className="flex min-h-7 items-center gap-2 pr-10">
              <SheetTitle>{ticker} Alerts</SheetTitle>
            </div>
          </SheetHeader>
          <div className="flex flex-col gap-4 px-4">
            <AlertSection direction="above" alert={aboveAlert} draft={aboveDraft} onDraftChange={setAboveDraft} onDeleteRequest={setDeleteTarget} />
            <AlertSection direction="below" alert={belowAlert} draft={belowDraft} onDraftChange={setBelowDraft} onDeleteRequest={setDeleteTarget} />
          </div>
          <SheetFooter className="flex-row justify-end gap-2">
            <Button variant="outline" className="w-20" onClick={handleCancel}>
              Cancel
            </Button>
            <Button className="w-20" onClick={handleSave} disabled={!anyDirty || isSaving}>
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this alert?</DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="w-20" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="w-20"
              onClick={async () => {
                if (!deleteTarget) return;
                try {
                  await deleteStockAlert(deleteTarget.id);
                  await mutate("/api/proxy/stockalerts");
                  // Clear this section's draft too — otherwise a stale draft
                  // still holding the deleted alert's price would look like
                  // a fresh create-candidate on the next Save, silently
                  // recreating what was just deleted.
                  const emptyDraft = draftFromAlert(undefined);
                  if (deleteTarget.direction === "above") setAboveDraft(emptyDraft);
                  else setBelowDraft(emptyDraft);
                  toast.success("Alert deleted");
                } catch (err) {
                  toast.error(err instanceof ApiError ? err.detail : "Failed to delete alert");
                } finally {
                  setDeleteTarget(null);
                }
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Price block */}
      <div className="flex flex-col gap-1">
        <div className="flex items-baseline gap-2">
          <Label className="font-ndot text-[32px] font-normal">{fmtCurrency(displayedPrice, detail.currency)}</Label>
          <Label className="text-muted-foreground">{detail.currency}</Label>
        </div>
        <Label style={{ color: changeColor }}>
          {isPositive ? "+" : "-"}${Math.abs(changeDollar).toFixed(2)} ({isPositive ? "+" : "-"}
          {Math.abs(changePercent).toFixed(2)}%)
        </Label>
      </div>

      {/* Chart */}
      <div className="flex flex-col gap-2">
        <MarketDetailChart
          key={selectedRange}
          data={chartData}
          avgCost={referenceCost}
          avgCostDate={avgCostDate}
          isPositive={isRangePositive}
          onHoverChange={setHoveredPoint}
        />
        <div className="flex items-center justify-between">
          <div className="flex gap-1">
            {DATE_RANGES.map((range) => (
              <Button
                key={range}
                variant={selectedRange === range ? "secondary" : "ghost"}
                className={selectedRange === range ? undefined : "text-muted-foreground"}
                onClick={() => setSelectedRange(range)}
              >
                {range}
              </Button>
            ))}
          </div>
          {marketOpen !== null && <Label className="text-muted-foreground text-sm">{marketOpen ? "Markets open" : "Markets closed"}</Label>}
        </div>
      </div>

      {/* Position summary — only when this ticker is held */}
      {position && (
        <div className="bg-card flex flex-col gap-4 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <Label className="text-lg font-medium">Stocks</Label>
            <div className="flex gap-1">
              <Button variant={returnWindow === "1D" ? "secondary" : "ghost"} onClick={() => setReturnWindow("1D")}>
                1D
              </Button>
              <Button variant={returnWindow === "All" ? "secondary" : "ghost"} onClick={() => setReturnWindow("All")}>
                All
              </Button>
            </div>
          </div>
          <div className="rounded-[12px] bg-muted/50 p-4">
            <div className="grid grid-cols-[1.6fr_0.8fr_1fr_1fr_1fr_1fr_1.4fr] gap-4 border-b pb-2">
              <Label className="text-muted-foreground text-[12px]">Position</Label>
              <Label className="text-muted-foreground text-[12px]">Currency</Label>
              <Label className="text-muted-foreground text-[12px]">Allocation</Label>
              <Label className="text-muted-foreground text-[12px]">Qty</Label>
              <Label className="text-muted-foreground text-[12px]">Price</Label>
              <Label className="text-muted-foreground text-[12px]">Total value</Label>
              <Label className="text-muted-foreground justify-self-end text-[12px]">
                {returnWindow === "1D" ? "Today's return" : "All time return"}
              </Label>
            </div>
            <div className="grid grid-cols-[1.6fr_0.8fr_1fr_1fr_1fr_1fr_1.4fr] items-center gap-4 pt-2">
              <Label className="text-[14px] font-medium">{position.shares} shares</Label>
              <Label className="text-[14px] font-normal">{position.currency}</Label>
              <Label className="text-[14px] font-normal">{allocationPct.toFixed(2)}%</Label>
              <Label className="text-[14px] font-normal">{position.shares}</Label>
              <Label className="text-[14px] font-normal">{fmtCurrency(position.currentPrice, position.currency)}</Label>
              <Label className="text-[14px] font-medium">{fmtCurrency(positionValue, position.currency)}</Label>
              <div className="flex items-center justify-self-end gap-2">
                <Label className="text-[14px] font-normal" style={{ color: positionGainColor }}>
                  {positionGainDollar >= 0 ? "+" : "-"}${Math.abs(positionGainDollar).toFixed(2)}
                </Label>
                <Label
                  className="rounded-md px-2 py-0.5 text-[12px] font-medium"
                  style={{ backgroundColor: `color-mix(in oklch, ${positionGainColor} 15%, transparent)`, color: positionGainColor }}
                >
                  {positionGainPercent.toFixed(2)}%
                </Label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Market details */}
      <div className="bg-card flex flex-col gap-4 rounded-lg p-4">
        <Label className="text-lg font-medium">Market details</Label>
        <div className="grid grid-cols-4 gap-4">
          <DetailField label="Open" value={fmtCurrency(detail.open, detail.currency)} />
          <DetailField label="Bid" value={`${fmtCurrency(detail.bid, detail.currency)} x ${detail.bidSize}`} />
          <DetailField label="Ask" value={`${fmtCurrency(detail.ask, detail.currency)} x ${detail.askSize}`} />
          <DetailField label="Last sale" value={fmtCurrency(detail.lastSale, detail.currency)} />
          <DetailField label="High" value={fmtCurrency(detail.high, detail.currency)} />
          <DetailField label="Low" value={fmtCurrency(detail.low, detail.currency)} />
          <DetailField label="Volume" value={fmtCompact(detail.volume)} />
          <DetailField label="Average volume" value={fmtCompact(detail.avgVolume)} />
          <DetailField label="52 week high" value={fmtCurrency(detail.week52High, detail.currency)} />
          <DetailField label="52 week low" value={fmtCurrency(detail.week52Low, detail.currency)} />
          <DetailField label="Exchange" value={detail.exchange} />
        </div>
      </div>

      {/* Dividends — only when the ticker has dividend data */}
      {detail.dividend && (
        <div className="bg-card flex flex-col gap-4 rounded-lg p-4">
          <Label className="text-lg font-medium">Dividends</Label>
          <div className="grid grid-cols-4 gap-4">
            <DetailField label="Frequency" value={detail.dividend.frequency} />
            <DetailField label="12-month yield" value={`${detail.dividend.yieldPct.toFixed(2)}%`} />
            <DetailField label="Ex-dividend date" value={detail.dividend.exDividendDate} />
            <DetailField label="Expected payment date" value={detail.dividend.paymentDate} />
          </div>
        </div>
      )}

      {/* Financials */}
      <div className="bg-card flex flex-col gap-4 rounded-lg p-4">
        <Label className="text-lg font-medium">Financials</Label>
        <div className="grid grid-cols-3 gap-4">
          <DetailField label="Market cap" value={fmtCompactCurrency(detail.marketCap, detail.currency)} />
          <DetailField label="Shares outstanding" value={fmtCompact(detail.sharesOutstanding)} />
          <DetailField label="P/E ratio" value={detail.peRatio.toFixed(2)} />
        </div>
      </div>

      {/* About */}
      <div className="bg-card flex flex-col gap-2 rounded-lg p-4">
        <Label className="text-lg font-medium">About {ticker}</Label>
        <p className="text-muted-foreground text-sm">{detail.about}</p>
      </div>

      {/* Recent activity — independent of Position: keyed on Activity rows existing for this ticker */}
      {activities.length > 0 && (
        <div className="flex flex-col gap-3">
          <Label className="text-lg font-medium">Recent activity</Label>
          {Object.entries(activityGroups).map(([date, group]) => (
            <div key={date} className="flex flex-col gap-2">
              <Label className="text-muted-foreground text-sm">
                {new Date(date).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
              </Label>
              {group.map((activity) => (
                <RecentActivityCard key={activity.id} activity={activity} logoColor={detail.logoColor} />
              ))}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
