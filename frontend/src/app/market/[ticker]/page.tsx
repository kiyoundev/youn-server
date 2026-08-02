"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { stockWatchlistData } from "@/lib/mock-portfolio";
import { MarketDetailChart, type ChartPoint } from "@/components/ui/market-detail-chart";
import { RecentActivityCard } from "@/components/ui/recent-activity-card";
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
import { Star } from "lucide-react";

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

export default function MarketDetailPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker;

  const [selectedRange, setSelectedRange] = useState<DateRange>("YTD");
  const [returnWindow, setReturnWindow] = useState<"1D" | "All">("All");
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<ChartPoint | null>(null);
  const [watchlisted, setWatchlisted] = useState(() => stockWatchlistData.some((a) => a.ticker === ticker));

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
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 shrink-0 rounded-lg" style={{ backgroundColor: detail.logoColor }} />
        <Label className="text-lg font-medium">{ticker}</Label>
        <Label className="text-muted-foreground">{detail.name}</Label>
        <button
          type="button"
          aria-label={watchlisted ? "Remove from watchlist" : "Add to watchlist"}
          aria-pressed={watchlisted}
          onClick={() => setWatchlisted((prev) => !prev)}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
        >
          <Star className={cn("size-4 shrink-0", watchlisted ? "fill-foreground opacity-100" : "opacity-50")} />
        </button>
      </div>

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
