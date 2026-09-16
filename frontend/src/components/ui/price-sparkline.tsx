"use client";

import { Line, LineChart, YAxis } from "recharts";

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
  // Scraper noise tolerance — different scrape paths for the same retailer
  // can record slightly different decimal precision for what's really the
  // same listed price (e.g. $799.99 vs $799.00), so a swing this small or
  // smaller is treated as unchanged rather than a real price move. Native-
  // currency units, so this is effectively USD/CAD-only in practice (KRW
  // amounts are large enough that $1 ~= exact-equality, no regression).
  const NOISE_THRESHOLD = 1;
  const diff = lastPrice - firstPrice;
  const color =
    Math.abs(diff) <= NOISE_THRESHOLD
      ? "var(--muted-foreground)"
      : diff < 0
        ? "var(--status-success)"
        : "var(--status-error)";

  const prices = data.map((d) => d.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const padding = (max - min) * 0.1 || max * 0.05;

  return (
    <LineChart width={width} height={height} data={data}>
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
