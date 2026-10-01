"use client";

import * as React from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { fmtPrice } from "@/lib/format";
import { flatPlotPrice } from "@/lib/price-noise";

interface Listing {
  retailer: string;
  priceHistory: { date: string; price: number }[];
}

interface ProductPriceChartProps {
  listings: Listing[];
  targetPrice?: number;
  // Issue #45 — currency is product-level (one value for the whole chart,
  // not per-listing/series) — fixes the tooltip's pre-existing missing-`$`
  // bug as a side effect. Native currency, never FX-converted (see
  // fmtPrice in lib/format.ts).
  currency?: string | null;
  height?: number;
  className?: string;
}

// CSS custom-property names can't safely contain arbitrary characters
// (e.g. the "." in "Amazon.ca") — this key drives generated CSS, so it's
// kept separate from the retailer name used for display (label/tooltip/legend).
const seriesKey = (retailer: string) => retailer.replace(/[^a-zA-Z0-9_-]/g, "_");
// Row key holding a point's real (un-flattened) price, read by the tooltip.
const realKey = (retailer: string) => `${seriesKey(retailer)}__real`;

function ProductPriceChart({
  listings,
  targetPrice,
  currency = null,
  height = 200,
  className,
}: ProductPriceChartProps) {
  const dates = Array.from(
    new Set(listings.flatMap((l) => l.priceHistory.map((h) => h.date))),
  ).sort();

  // Issue #62 — a listing whose history stays within the noise band
  // (lib/price-noise.ts) is plotted flat at its latest price. The real
  // price still rides along under realKey so the tooltip never shows the
  // flattened value.
  const flatByListing = new Map(
    listings.map((l) => [l.retailer, flatPlotPrice(l.priceHistory.map((h) => h.price))]),
  );

  const data = dates.map((date) => {
    const row: Record<string, string | number> = { date };
    listings.forEach((l) => {
      const point = l.priceHistory.find((h) => h.date === date);
      if (point) {
        row[seriesKey(l.retailer)] = flatByListing.get(l.retailer) ?? point.price;
        row[realKey(l.retailer)] = point.price;
      }
    });
    return row;
  });

  // Domain is fit to price data only, never targetPrice — a target far
  // below/above the actual price range used to drag the axis wide enough
  // that a real (if small) price move flattened out to invisible. A
  // target that falls outside this domain just isn't drawn at all (see
  // targetInRange below) rather than forcing the axis wide to fit it.
  // Fit to the plotted (possibly flattened) values, not the raw history.
  const allPrices = listings.flatMap((l) => {
    const flat = flatByListing.get(l.retailer);
    return l.priceHistory.map((h) => flat ?? h.price);
  });
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const paddedMin = rawMin - (rawMin > 0 ? rawMin * 0.05 : 0);
  const paddedMax = rawMax + rawMax * 0.05;

  const targetInRange =
    targetPrice !== undefined && targetPrice >= paddedMin && targetPrice <= paddedMax;

  const chartConfig = listings.reduce((config, listing, i) => {
    config[seriesKey(listing.retailer)] = {
      label: listing.retailer,
      color: `var(--chart-${(i % 5) + 1})`,
    };
    return config;
  }, {} as ChartConfig);

  return (
    <div className="relative" style={{ height, width: "100%" }}>
      <ChartContainer
        config={chartConfig}
        className={className}
        style={{ height, width: "100%" }}
      >
        <LineChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 4, left: 12 }}
        >
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(value) =>
              new Date(value as string).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })
            }
            tickLine={false}
            axisLine={false}
          />
          <YAxis domain={[paddedMin, paddedMax]} hide />
          {targetInRange && (
            <ReferenceLine
              y={targetPrice}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
          )}
          <ChartTooltip
            content={
              <ChartTooltipContent
                className="min-w-44"
                labelFormatter={(value) =>
                  new Date(value as string).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })
                }
                // ChartTooltipContent's `formatter`, when supplied, replaces
                // the *entire* row (indicator dot + name + value), not just
                // the value text (see chart.tsx) — this mirrors its default
                // "dot" indicator row exactly (the only indicator variant
                // this chart ever uses), just with fmtPrice() for the value
                // instead of a bare .toLocaleString() (issue #45 — fixes the
                // tooltip's pre-existing missing-`$` bug).
                formatter={(value, name, item) => {
                  const indicatorColor = item.payload?.fill ?? item.color;
                  const realPrice = item.payload?.[realKey(String(name))];
                  return (
                    <>
                      <div
                        className="h-2.5 w-2.5 shrink-0 rounded-[2px] border-(--color-border) bg-(--color-bg)"
                        style={
                          {
                            "--color-bg": indicatorColor,
                            "--color-border": indicatorColor,
                          } as React.CSSProperties
                        }
                      />
                      <div className="flex flex-1 items-center justify-between leading-none">
                        <span className="text-muted-foreground">{name}</span>
                        <span className="font-mono font-medium text-foreground tabular-nums">
                          {fmtPrice(Number(realPrice ?? value), currency)}
                        </span>
                      </div>
                    </>
                  );
                }}
              />
            }
          />
          {listings.map((listing) => (
            <Line
              key={listing.retailer}
              type="monotone"
              dataKey={seriesKey(listing.retailer)}
              // Recharts defaults a series' tooltip `name` to its
              // `dataKey` when none is given — that's the CSS-safe
              // seriesKey (non-ASCII chars replaced with "_"), not the
              // real retailer name. The default ChartTooltipContent path
              // resolves the real name via chartConfig, but this chart's
              // custom `formatter` below reads `name` directly, so a
              // Hangul-heavy retailer name rendered as underscores
              // without this explicit override.
              name={listing.retailer}
              stroke={`var(--color-${seriesKey(listing.retailer)})`}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ChartContainer>
    </div>
  );
}

export { ProductPriceChart };
