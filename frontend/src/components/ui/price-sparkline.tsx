"use client";

import { Line, LineChart, YAxis } from "recharts";
import { PRICE_NOISE_THRESHOLD, flatPlotPrice } from "@/lib/price-noise";

interface PriceSparklineProps {
  data: { date: string; price: number }[];
  width?: number;
  height?: number;
}

function PriceSparkline({ data, width = 64, height = 24 }: PriceSparklineProps) {
  if (data.length < 2) {
    return <span className="text-brand-300 text-xs">—</span>;
  }

  const firstPrice = data[0].price;
  const lastPrice = data[data.length - 1].price;
  // Scraper noise tolerance (see lib/price-noise.ts) — a swing this small
  // or smaller is treated as unchanged rather than a real price move.
  const diff = lastPrice - firstPrice;
  const color =
    Math.abs(diff) <= PRICE_NOISE_THRESHOLD
      ? "var(--muted-foreground)"
      : diff < 0
        ? "var(--status-success)"
        : "var(--status-error)";

  // Issue #62 — a series that never leaves the noise band is drawn as a
  // truly flat line, not stretched to fill the chart height (the axis fits
  // tightly to the data, so even a $1 wiggle would otherwise spike).
  const flat = flatPlotPrice(data.map((d) => d.price));
  const plotted = flat === null ? data : data.map((d) => ({ ...d, price: flat }));

  const prices = plotted.map((d) => d.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const padding = (max - min) * 0.1 || max * 0.05;

  return (
    <LineChart width={width} height={height} data={plotted}>
      <YAxis domain={[min - padding, max + padding]} hide />
      <Line
        type="monotone"
        dataKey="price"
        stroke={color}
        strokeWidth={1.5}
        dot={false}
        activeDot={false}
        isAnimationActive={false}
      />
    </LineChart>
  );
}

export { PriceSparkline };
