"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { Plus } from "lucide-react";
import { PortfolioLineChart } from "@/components/ui/portfolio-line-chart";
import { AllocationDonutChart } from "@/components/ui/allocation-donut-chart";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext, type CarouselApi } from "@/components/ui/carousel";
import { stockWatchlistData } from "@/lib/mock-portfolio";
import { mockMarketDetails } from "@/lib/mock-market";
import { POLL_INTERVAL_MS } from "@/lib/polling";
import { DATE_RANGES, type DateRange } from "@/lib/api/market";
import {
  POSITIONS_KEY,
  PORTFOLIO_SUMMARY_KEY,
  getPositions,
  getPortfolioSummary,
  getPortfolioHistory,
  type Position,
  type PortfolioSummary,
  type PortfolioHistoryPoint,
  type PriceStatus,
} from "@/lib/api/positions";
import { TickerLogo } from "@/components/ui/ticker-logo";
import { Spinner } from "@/components/ui/loading-screen";
import { ApiError } from "@/lib/api/api-client";

const allocationData = [
  { category: "Stocks", value: 60, thickness: 25 },
  { category: "ETF", value: 20 },
  { category: "GIC", value: 12 },
  { category: "Cash", value: 8 },
];

// Curated tickers featured on this page — full company/market data lives in
// mock-market.ts (single source of truth, also used by /market/[ticker]).
const POPULAR_ASSET_TICKERS: (keyof typeof mockMarketDetails)[] = ["AAPL", "NVDA", "SPY", "QQQ"];

function fmtCompact(value: number) {
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
}

// Money in the holding's own currency, with the code ("USD 210.00"), as before.
function fmtMoney(value: number, currency: string) {
  return value.toLocaleString("en-US", { style: "currency", currency, currencyDisplay: "code" });
}

// Whole shares from 1 up; two decimals below 1 so a small holding never reads "0".
function fmtShares(shares: number) {
  return shares.toLocaleString("en-US", { maximumFractionDigits: shares < 1 ? 2 : 0 });
}

function fmtMonth(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

// Dollars with cents, for the summary figures ($8.06): small cash balances must not round to $8.
function fmtDollars(value: number) {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Tooltip for a row whose price is old or missing; undefined when the price is fresh.
function priceNote(status: PriceStatus, asOf: string | null) {
  switch (status) {
    case "stale": {
      const at = asOf && new Date(asOf).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
      return at ? `Last known price, as of ${at}` : "Last known price";
    }
    case "unavailable":
      return "No price available right now";
    case "currency_mismatch":
      return "The price source reported a different currency, so the price is withheld";
    default:
      return undefined;
  }
}

export default function PortfolioPage() {
  const [selectedRange, setSelectedRange] = useState<DateRange>("1W");
  const [popularAssetsApi, setPopularAssetsApi] = useState<CarouselApi>();
  const [canScrollPrev, setCanScrollPrev] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);

  // Two independent keys, so one failing doesn't blank the other. Both routes
  // price through the same shared 15s server cache, so the pair costs one
  // upstream lookup per symbol. Polled, no SSE (#19).
  const {
    data: positions,
    error: positionsError,
    isLoading: positionsLoading,
  } = useSWR<Position[]>(POSITIONS_KEY, getPositions, { refreshInterval: POLL_INTERVAL_MS });
  const {
    data: summary,
    error: summaryError,
    isLoading: summaryLoading,
  } = useSWR<PortfolioSummary>(PORTFOLIO_SUMMARY_KEY, getPortfolioSummary, { refreshInterval: POLL_INTERVAL_MS });

  // No refreshInterval — a past point never changes; only a range change (new key) refetches.
  const { data: history } = useSWR(["/api/proxy/portfolio/history", selectedRange], () => getPortfolioHistory(selectedRange));

  // Null while unhovered — PortfolioLineChart fires this on mount too (with
  // null), which is what resets this back to "unhovered" on a range change
  // (the chart remounts via key={selectedRange} below).
  const [hoveredPoint, setHoveredPoint] = useState<PortfolioHistoryPoint | null>(null);

  // Both the headline $ and the %/$ badge track the hovered point; unhovered,
  // both default to the selected range's own latest point.
  const activePoint = hoveredPoint ?? (history && history.length > 0 ? history[history.length - 1] : null);
  const headlineBalanceCad = activePoint ? activePoint.value : summary?.balance_cad;

  // Raw value diff minus net deposits over the same stretch — a deposit
  // elsewhere in the range inflates "value" but not "total_deposits_cad"'s
  // own diff, so it cancels out instead of reading as a gain. The % denominator
  // is deposits-to-date (not range-start value): verified against a real
  // Wealthsimple account, where this reproduces its reported % exactly.
  // Guarded the same way unrealized_gain_pct guards a zero/missing divisor
  // elsewhere in this app.
  const rangeStart = history?.[0];
  const rangeChangeDollar =
    activePoint && rangeStart
      ? activePoint.value - rangeStart.value - (activePoint.total_deposits_cad - rangeStart.total_deposits_cad)
      : null;
  const rangeChangePct = rangeChangeDollar !== null && activePoint?.total_deposits_cad ? rangeChangeDollar / activePoint.total_deposits_cad : null;
  const isRangeZero = rangeChangePct === 0;
  const isRangeUp = rangeChangePct !== null && rangeChangePct > 0;
  const rangeChangeColor =
    rangeChangePct === null || isRangeZero ? "var(--status-neutral)" : isRangeUp ? "var(--status-success)" : "var(--status-error)";
  const rangeChangeSign = isRangeZero ? "" : isRangeUp ? "+" : "-";
  const rangeChangeText =
    rangeChangePct === null
      ? "—"
      : `${rangeChangeSign}${fmtDollars(Math.abs(rangeChangeDollar!))} (${rangeChangeSign}${Math.abs(rangeChangePct * 100).toFixed(2)}%)`;

  // Tracks the Popular Assets carousel's own prev/next button state — synced
  // to popularAssetsApi (embla), not to anything this page owns. Re-subscribes
  // only when the api instance itself changes (mounts once carousel is ready).
  useEffect(() => {
    if (!popularAssetsApi) return;
    const onSelect = () => {
      setCanScrollPrev(popularAssetsApi.canScrollPrev());
      setCanScrollNext(popularAssetsApi.canScrollNext());
    };
    onSelect();
    popularAssetsApi.on("select", onSelect);
    popularAssetsApi.on("reInit", onSelect);
    return () => {
      popularAssetsApi.off("select", onSelect);
      popularAssetsApi.off("reInit", onSelect);
    };
  }, [popularAssetsApi]);

  // "q" cycles the chart's date-range selector — a page-wide window listener,
  // unrelated to the carousel above (different target, different lifecycle:
  // attaches once on mount, [] dep, never re-subscribes). Kept as its own
  // effect rather than merged with the one above so this doesn't get torn
  // down/re-attached every time popularAssetsApi changes.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && ["INPUT", "TEXTAREA"].includes(e.target.tagName)) {
        return;
      }
      if (e.key.toLowerCase() === "q") {
        setSelectedRange((prev) => {
          const nextIndex = (DATE_RANGES.indexOf(prev) + 1) % DATE_RANGES.length;
          return DATE_RANGES[nextIndex];
        });
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <main className="p-5 gap-4 flex flex-col">
      <div className="flex w-full gap-20">
        {/* Overview Left Section */}
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-4">
            <Label className="font-ndot text-[40px] font-normal block">
              {headlineBalanceCad != null ? fmtDollars(headlineBalanceCad) : summaryLoading ? "…" : "—"}
            </Label>
            <div className="flex gap-2">
              <Label className="text-base" style={{ color: rangeChangeColor }}>{rangeChangeText}</Label>
            </div>
          </div>
          <div className="flex gap-20" title={summaryError ? "Couldn't load the summary" : undefined}>
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{positions ? positions.length : positionsLoading ? "…" : "—"}</Label>
              <Label className="text-muted-foreground">Companies</Label>
            </div>
            {/* Balance is the cash left over; Committed is what the held shares cost in CAD when bought. */}
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{summary ? fmtDollars(summary.cash_cad) : summaryLoading ? "…" : "—"}</Label>
              <Label className="text-muted-foreground">Balance</Label>
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{summary ? fmtDollars(summary.invested_cad) : summaryLoading ? "…" : "—"}</Label>
              <Label className="text-muted-foreground">Committed</Label>
            </div>
          </div>
        </div>
        {/* Overview Middle Section */}
        <div className="relative flex w-[150px] shrink-0 items-center justify-center">
          <AllocationDonutChart data={allocationData} />
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <Label className="font-ndot text-lg font-medium">36%</Label>
            <Label className="text-muted-foreground">Growth Rate</Label>
          </div>
        </div>
        {/* Overview Right Section */}
        <div className="flex-1">
          <PortfolioLineChart
            key={selectedRange}
            data={history ?? []}
            investedAmount={summary?.invested_cad}
            onHoverChange={setHoveredPoint}
          />
          <div className="flex justify-end gap-1">
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
        </div>
      </div>
      <div className="flex flex-col bg-card p-4 rounded-lg gap-4">
        <Carousel opts={{ align: "start" }} setApi={setPopularAssetsApi} className="w-full">
          <div className="flex items-center justify-between">
            <Label className="text-lg font-medium">Popular Assets</Label>
            <div className="flex gap-2">
              <CarouselPrevious className="static rounded-lg" />
              <CarouselNext className="static rounded-lg" />
            </div>
          </div>
          <div
            style={{
              maskImage: `linear-gradient(to right, ${canScrollPrev ? "transparent, black 32px" : "black"}, ${
                canScrollNext ? "black calc(100% - 32px), transparent" : "black"
              })`,
              WebkitMaskImage: `linear-gradient(to right, ${canScrollPrev ? "transparent, black 32px" : "black"}, ${
                canScrollNext ? "black calc(100% - 32px), transparent" : "black"
              })`,
            }}
          >
            <CarouselContent className="-ml-4 mt-2">
              {POPULAR_ASSET_TICKERS.map((ticker) => {
                const asset = mockMarketDetails[ticker];
                const changeAmount = asset.currentPrice - asset.open;
                const changePercent = asset.open !== 0 ? (changeAmount / asset.open) * 100 : 0;
                const isChangeUp = changePercent > 0;
                const changeColor = isChangeUp ? "var(--status-success)" : "var(--status-error)";
                return (
                  <CarouselItem key={ticker} className="basis-[350px]">
                    <Card className="p-3 bg-muted/50 ring-inset">
                      <div className="flex items-stretch gap-2">
                        <div
                          className="h-[50px] w-[50px] rounded flex items-center justify-center text-white font-medium"
                          style={{ backgroundColor: asset.logoColor }}
                        >
                          {ticker.replace("^", "").slice(0, 1)}
                        </div>
                        <div className="flex flex-col flex-1 justify-between p-1">
                          <div className="flex items-center gap-2">
                            <Label className="h-5 items-center text-[14px] font-normal">{asset.name}</Label>
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                              {asset.assetCategory}
                            </Badge>
                          </div>
                          <div className="flex h-4 items-stretch gap-1.5">
                            {asset.marketCap > 0 && (
                              <Label className="items-center text-[12px] font-normal text-brand-500">{fmtCompact(asset.marketCap)} Cap</Label>
                            )}
                            {asset.marketCap > 0 && asset.volume > 0 && <Separator orientation="vertical" />}
                            {asset.volume > 0 && (
                              <Label className="items-center text-[12px] font-normal text-brand-500">Vol {fmtCompact(asset.volume)}</Label>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col justify-center">
                          <Label className="h-5 items-center whitespace-nowrap text-[14px] font-normal">
                            {asset.currentPrice.toLocaleString("en-US", {
                              style: "currency",
                              currency: asset.currency,
                              currencyDisplay: "code",
                            })}
                          </Label>
                          <Label className="h-4 items-center whitespace-nowrap text-[12px] font-normal" style={{ color: changeColor }}>
                            {isChangeUp ? "+" : ""}
                            {changePercent.toFixed(2)}% ({isChangeUp ? "+" : ""}
                            {changeAmount.toFixed(2)})
                          </Label>
                        </div>
                      </div>
                      <Button variant="outline" className="border-0" render={<Link href={`/market/${encodeURIComponent(ticker)}`} />}>
                        View Details
                      </Button>
                    </Card>
                  </CarouselItem>
                );
              })}
            </CarouselContent>
          </div>
        </Carousel>
      </div>
      {/* Bottom Section */}
      <div className="flex gap-4 w-full">
        {/* Holdings Tile */}
        <div className="bg-card rounded-lg p-4 flex-1 flex flex-col gap-4">
          <div className="flex h-5 items-center justify-between">
            <Label className="text-lg font-medium">Holdings</Label>
            {/* A failed poll keeps the last data on screen (SWR); say so, or old numbers look current. */}
            {positionsError && positions && (
              <Label className="text-[12px] font-normal text-muted-foreground">
                Couldn&apos;t refresh. Showing the last data.
              </Label>
            )}
          </div>
          <div className="rounded-[12px] bg-muted/50 divide-y divide-[#383939]">
            {positionsError && !positions ? (
              <div className="flex flex-col items-center justify-center gap-1 p-8 text-center">
                <Label className="text-[14px] font-normal">Couldn&apos;t load holdings</Label>
                <Label className="text-[12px] font-normal text-muted-foreground">
                  {positionsError instanceof ApiError ? positionsError.detail : "The server didn't answer. It will retry shortly."}
                </Label>
              </div>
            ) : positionsLoading ? (
              <div className="flex items-center justify-center p-8">
                <Spinner className="size-5 text-muted-foreground" />
              </div>
            ) : positions?.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-1 p-8 text-center">
                <Label className="text-[14px] font-normal">No holdings yet</Label>
                <Label className="text-[12px] font-normal text-muted-foreground">
                  Import your Wealthsimple activities export (CSV) with the upload button in the top bar.
                </Label>
              </div>
            ) : (
              positions?.map((position) => {
              const { native_currency: currency, market_value: value } = position;
              const gain = position.unrealized_gain;
              const pct = position.unrealized_gain_pct;
              const isZero = gain === 0;
              const isUp = gain !== null && gain > 0;
              const sign = isZero ? "" : isUp ? "+" : "-";
              const changeColor = gain === null || isZero ? "var(--status-neutral)" : isUp ? "var(--status-success)" : "var(--status-error)";
              // pct is a fraction, and null for a zero-cost holding (then only the dollar gain shows)
              const dollars = gain === null ? "" : `$${Math.abs(gain).toFixed(2)}`;
              const gainText = gain === null ? "—" : pct === null ? `${sign}${dollars}` : `${sign}${Math.abs(pct * 100).toFixed(2)}% (${dollars})`;
              const shares = fmtShares(position.shares);
              const note = priceNote(position.price_status, position.price_as_of);
              return (
                <Link
                  key={`${position.symbol}-${currency}`}
                  href={`/market/${encodeURIComponent(position.symbol)}`}
                  className="flex min-h-[60px] items-stretch gap-3 p-3"
                >
                  <TickerLogo symbol={position.symbol} currency={currency} />
                  <div className="flex flex-col flex-1 justify-between py-1">
                    <Label className="h-5 items-center text-[14px] font-normal">{position.symbol}</Label>
                    <div className="flex h-4 items-stretch gap-1.5">
                      <Label className="items-center text-[12px] font-normal text-brand-500">
                        {shares} {shares === "1" ? "Share" : "Shares"}
                      </Label>
                      <Separator orientation="vertical" />
                      <Label className="items-center text-[12px] font-normal text-brand-500">Last traded {fmtMonth(position.last_traded_at)}</Label>
                    </div>
                  </div>

                  {position.asset_type && (
                    <Badge variant="outline" className="self-center text-[10px] px-1.5 py-0">
                      {position.asset_type}
                    </Badge>
                  )}
                  <div
                    title={note}
                    className={`flex flex-col items-end justify-center min-w-[100px]${note ? " cursor-help" : ""}${
                      position.price_status === "stale" ? " opacity-60" : ""
                    }`}
                  >
                    <Label className="h-5 items-center whitespace-nowrap text-[14px] font-normal">
                      {value === null ? "—" : fmtMoney(value, currency)}
                    </Label>
                    <Label className="h-4 items-center whitespace-nowrap text-[12px] font-normal" style={{ color: changeColor }}>
                      {gainText}
                    </Label>
                  </div>
                </Link>
              );
              })
            )}
          </div>
        </div>
        {/* Watchlist Tile */}
        <div className="bg-card rounded-lg p-4 flex-1 flex flex-col gap-4">
          <div className="flex h-5 items-center justify-between">
            <Label className="text-lg font-medium">Watchlist</Label>
            <button aria-label="Add item">
              <Plus className="text-brand-200" size={20} strokeWidth={1.25} />
            </button>
          </div>
          <div className="rounded-[12px] bg-muted/50 divide-y divide-[#383939]">
            {stockWatchlistData.map((alert) => {
              const changePercent = ((alert.currentPrice - alert.targetPrice) / alert.targetPrice) * 100;
              const changeDollar = alert.currentPrice - alert.targetPrice;
              const isZero = changePercent === 0;
              const isUp = changePercent > 0;
              const sign = isZero ? "" : isUp ? "+" : "-";
              const changeColor = isZero ? "var(--status-neutral)" : isUp ? "var(--status-success)" : "var(--status-error)";
              return (
                <Link key={alert.ticker} href={`/market/${encodeURIComponent(alert.ticker)}`} className="flex min-h-[68px] items-stretch gap-3 p-3">
                  <div className="h-[30px] w-[30px] self-center rounded bg-white" />
                  <div className="flex flex-col flex-1 justify-center py-1">
                    <Label className="h-5 items-center text-[14px] font-normal">{alert.ticker}</Label>
                  </div>
                  <Badge variant="outline" className="self-center text-[10px] px-1.5 py-0">
                    {alert.category}
                  </Badge>
                  <div className="flex flex-col items-end justify-center min-w-[100px]">
                    <Label className="h-5 items-center whitespace-nowrap text-[14px] font-normal">
                      {alert.currentPrice.toLocaleString("en-US", {
                        style: "currency",
                        currency: "USD",
                        currencyDisplay: "code",
                      })}
                    </Label>
                    <Label className="h-4 items-center whitespace-nowrap text-[12px] font-normal" style={{ color: changeColor }}>
                      {sign}
                      {Math.abs(changePercent).toFixed(2)}% (${Math.abs(changeDollar).toFixed(2)})
                    </Label>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </main>
  );
}
