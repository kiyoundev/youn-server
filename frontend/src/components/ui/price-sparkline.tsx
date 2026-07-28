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
  const color =
    lastPrice === firstPrice
      ? "var(--muted-foreground)"
      : lastPrice < firstPrice
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
