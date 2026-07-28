"use client";

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

interface Listing {
  retailer: string;
  priceHistory: { date: string; price: number }[];
}

interface ProductPriceChartProps {
  listings: Listing[];
  targetPrice?: number;
  height?: number;
  className?: string;
}

// CSS custom-property names can't safely contain arbitrary characters
// (e.g. the "." in "Amazon.ca") — this key drives generated CSS, so it's
// kept separate from the retailer name used for display (label/tooltip/legend).
const seriesKey = (retailer: string) => retailer.replace(/[^a-zA-Z0-9_-]/g, "_");

function ProductPriceChart({
  listings,
  targetPrice,
  height = 200,
  className,
}: ProductPriceChartProps) {
  const dates = Array.from(
    new Set(listings.flatMap((l) => l.priceHistory.map((h) => h.date))),
  ).sort();

  const data = dates.map((date) => {
    const row: Record<string, string | number> = { date };
    listings.forEach((l) => {
      const point = l.priceHistory.find((h) => h.date === date);
      if (point) row[seriesKey(l.retailer)] = point.price;
    });
    return row;
  });

  const allPrices = listings.flatMap((l) => l.priceHistory.map((h) => h.price));
  if (targetPrice !== undefined) allPrices.push(targetPrice);
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const paddedMin = rawMin - (rawMin > 0 ? rawMin * 0.05 : 0);
  const paddedMax = rawMax + rawMax * 0.05;

  const chartConfig = listings.reduce((config, listing, i) => {
    config[seriesKey(listing.retailer)] = {
      label: listing.retailer,
      color: `var(--chart-${(i % 5) + 1})`,
    };
    return config;
  }, {} as ChartConfig);

  return (
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
        {targetPrice !== undefined && (
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
            />
          }
        />
        {listings.map((listing) => (
          <Line
            key={listing.retailer}
            type="monotone"
            dataKey={seriesKey(listing.retailer)}
            stroke={`var(--color-${seriesKey(listing.retailer)})`}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}

export { ProductPriceChart };
