"use client";

import { useEffect, useState } from "react";
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
import { holdingsData, stockWatchlistData } from "@/lib/mock-portfolio";
import { mockMarketDetails } from "@/lib/mock-market";

const allocationData = [
  { category: "Stocks", value: 60, thickness: 25 },
  { category: "ETF", value: 20 },
  { category: "GIC", value: 12 },
  { category: "Cash", value: 8 },
];

const currentValueChangePercent: number = 2.5;

// Curated tickers featured on this page — full company/market data lives in
// mock-market.ts (single source of truth, also used by /market/[ticker]).
const POPULAR_ASSET_TICKERS: (keyof typeof mockMarketDetails)[] = ["AAPL", "NVDA", "SPY", "QQQ", "^GSPC"];

function fmtCompact(value: number) {
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
}

type DateRange = "1D" | "1W" | "1M" | "3M" | "6M" | "YTD" | "ALL";

const DATE_RANGES: DateRange[] = ["1D", "1W", "1M", "3M", "6M", "YTD", "ALL"];

const chartDataByRange: Record<DateRange, { date: string; value: number }[]> = {
  "1D": [
    { date: "2026-07-27T09:30", value: 58900 },
    { date: "2026-07-27T10:30", value: 59200 },
    { date: "2026-07-27T11:30", value: 58700 },
    { date: "2026-07-27T12:30", value: 59400 },
    { date: "2026-07-27T13:30", value: 59600 },
    { date: "2026-07-27T14:30", value: 59000 },
    { date: "2026-07-27T15:30", value: 59300 },
    { date: "2026-07-27T16:00", value: 59100 },
  ],
  "1W": [
    { date: "2026-07-21", value: 56200 },
    { date: "2026-07-22", value: 55400 },
    { date: "2026-07-23", value: 57100 },
    { date: "2026-07-24", value: 56300 },
    { date: "2026-07-25", value: 58200 },
    { date: "2026-07-26", value: 57600 },
    { date: "2026-07-27", value: 59100 },
  ],
  "1M": [
    { date: "2026-07-01", value: 48200 },
    { date: "2026-07-02", value: 47650 },
    { date: "2026-07-03", value: 48900 },
    { date: "2026-07-04", value: 49200 },
    { date: "2026-07-05", value: 48100 },
    { date: "2026-07-06", value: 50300 },
    { date: "2026-07-07", value: 49800 },
    { date: "2026-07-08", value: 51200 },
    { date: "2026-07-09", value: 50100 },
    { date: "2026-07-10", value: 52400 },
    { date: "2026-07-11", value: 51800 },
    { date: "2026-07-12", value: 49600 },
    { date: "2026-07-13", value: 50900 },
    { date: "2026-07-14", value: 52100 },
    { date: "2026-07-15", value: 53400 },
    { date: "2026-07-16", value: 52700 },
    { date: "2026-07-17", value: 54200 },
    { date: "2026-07-18", value: 53100 },
    { date: "2026-07-19", value: 55600 },
    { date: "2026-07-20", value: 54900 },
    { date: "2026-07-21", value: 56200 },
    { date: "2026-07-22", value: 55400 },
    { date: "2026-07-23", value: 57100 },
    { date: "2026-07-24", value: 56300 },
    { date: "2026-07-25", value: 58200 },
    { date: "2026-07-26", value: 57600 },
    { date: "2026-07-27", value: 59100 },
  ],
  "3M": [
    { date: "2026-05-01", value: 41200 },
    { date: "2026-05-15", value: 43600 },
    { date: "2026-06-01", value: 42100 },
    { date: "2026-06-15", value: 45800 },
    { date: "2026-07-01", value: 48200 },
    { date: "2026-07-15", value: 53400 },
    { date: "2026-07-27", value: 59100 },
  ],
  "6M": [
    { date: "2026-02-01", value: 33400 },
    { date: "2026-02-15", value: 35100 },
    { date: "2026-03-01", value: 34200 },
    { date: "2026-03-15", value: 37800 },
    { date: "2026-04-01", value: 39600 },
    { date: "2026-04-15", value: 38100 },
    { date: "2026-05-01", value: 41200 },
    { date: "2026-05-15", value: 43600 },
    { date: "2026-06-01", value: 42100 },
    { date: "2026-06-15", value: 45800 },
    { date: "2026-07-01", value: 48200 },
    { date: "2026-07-27", value: 59100 },
  ],
  YTD: [
    { date: "2026-01-01", value: 28900 },
    { date: "2026-01-15", value: 30200 },
    { date: "2026-02-01", value: 33400 },
    { date: "2026-02-15", value: 35100 },
    { date: "2026-03-01", value: 34200 },
    { date: "2026-03-15", value: 37800 },
    { date: "2026-04-01", value: 39600 },
    { date: "2026-04-15", value: 38100 },
    { date: "2026-05-01", value: 41200 },
    { date: "2026-05-15", value: 43600 },
    { date: "2026-06-01", value: 42100 },
    { date: "2026-06-15", value: 45800 },
    { date: "2026-07-01", value: 48200 },
    { date: "2026-07-27", value: 59100 },
  ],
  ALL: [
    { date: "2024-01-01", value: 8200 },
    { date: "2024-07-01", value: 12600 },
    { date: "2025-01-01", value: 15400 },
    { date: "2025-07-01", value: 21900 },
    { date: "2026-01-01", value: 28900 },
    { date: "2026-04-01", value: 39600 },
    { date: "2026-07-27", value: 59100 },
  ],
};

export default function PortfolioPage() {
  const [selectedRange, setSelectedRange] = useState<DateRange>("1W");
  const [popularAssetsApi, setPopularAssetsApi] = useState<CarouselApi>();
  const [canScrollPrev, setCanScrollPrev] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);

  const isChangeZero = currentValueChangePercent === 0;
  const isChangeUp = currentValueChangePercent > 0;
  const changeSign = isChangeZero ? "" : isChangeUp ? "+" : "-";
  const changeColor = isChangeZero ? "var(--status-neutral)" : isChangeUp ? "var(--status-success)" : "var(--status-error)";

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
            <Label className="font-ndot text-[40px] font-normal block">$150,000</Label>
            <div className="flex gap-2">
              <Label className="text-muted-foreground">Current Value</Label>
              <Label className="font-ndot" style={{ color: changeColor }}>
                {changeSign}
                {Math.abs(currentValueChangePercent).toFixed(2)}%
              </Label>
            </div>
          </div>
          <div className="flex gap-20">
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">{holdingsData.length}</Label>
              <Label className="text-muted-foreground">Companies</Label>
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">$8,000</Label>
              <Label className="text-muted-foreground">Balance</Label>
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-md font-ndot">$5,000</Label>
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
          <PortfolioLineChart data={chartDataByRange[selectedRange]} />
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
                            {asset.volume > 0 && <Label className="items-center text-[12px] font-normal text-brand-500">Vol {fmtCompact(asset.volume)}</Label>}
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
          <div className="flex h-5 items-center">
            <Label className="text-lg font-medium">Holdings</Label>
          </div>
          <div className="rounded-[12px] bg-muted/50 divide-y divide-[#383939]">
            {holdingsData.map((position) => {
              const changePercent = ((position.currentPrice - position.avgPrice) / position.avgPrice) * 100;
              const changeDollar = (position.currentPrice - position.avgPrice) * position.shares;
              const isZero = changePercent === 0;
              const isUp = changePercent > 0;
              const sign = isZero ? "" : isUp ? "+" : "-";
              const changeColor = isZero ? "var(--status-neutral)" : isUp ? "var(--status-success)" : "var(--status-error)";
              return (
                <Link
                  key={position.symbol}
                  href={`/market/${encodeURIComponent(position.symbol)}`}
                  className="flex min-h-[60px] items-stretch gap-3 p-3"
                >
                  <div className="h-[30px] w-[30px] self-center rounded bg-white" />
                  <div className="flex flex-col flex-1 justify-between py-1">
                    <Label className="h-5 items-center text-[14px] font-normal">{position.symbol}</Label>
                    <div className="flex h-4 items-stretch gap-1.5">
                      <Label className="items-center text-[12px] font-normal text-brand-500">{position.shares} Shares</Label>
                      <Separator orientation="vertical" />
                      <Label className="items-center text-[12px] font-normal text-brand-500">
                        {new Date(position.purchasedAt).toLocaleDateString("en-US", {
                          month: "short",
                          year: "numeric",
                        })}
                      </Label>
                    </div>
                  </div>

                  <Badge variant="outline" className="self-center text-[10px] px-1.5 py-0">
                    {position.assetType}
                  </Badge>
                  <div className="flex flex-col items-end justify-center min-w-[100px]">
                    <Label className="h-5 items-center whitespace-nowrap text-[14px] font-normal">
                      {position.currentPrice.toLocaleString("en-US", {
                        style: "currency",
                        currency: position.currency,
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
                <Link
                  key={alert.ticker}
                  href={`/market/${encodeURIComponent(alert.ticker)}`}
                  className="flex min-h-[68px] items-stretch gap-3 p-3"
                >
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
