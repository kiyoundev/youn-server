"use client";

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

interface PortfolioLineChartProps {
  data: { date: string; value: number }[];
  height?: number;
  className?: string;
}

const chartConfig = {
  value: {
    label: "Value",
    color: "var(--brand-200)",
  },
} satisfies ChartConfig;

function PortfolioLineChart({
  data,
  height = 120,
  className,
}: PortfolioLineChartProps) {
  const values = data.map((d) => d.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const paddedMin = rawMin - (rawMin > 0 ? rawMin * 0.02 : 0);
  const paddedMax = rawMax + rawMax * 0.02;
  const tickCount = 5;
  const ticks = Array.from({ length: tickCount }, (_, i) =>
    paddedMin + ((paddedMax - paddedMin) * i) / (tickCount - 1),
  );

  const marginTop = 8;
  const marginBottom = 4;
  const plotHeight = height - marginTop - marginBottom;
  const horizontalPoints = Array.from(
    { length: tickCount },
    (_, i) => marginTop + (plotHeight * i) / (tickCount - 1),
  );

  return (
    <ChartContainer
      config={chartConfig}
      className={className}
      style={{ height, width: "100%" }}
      data-slot="portfolio-line-chart"
    >
      <LineChart
        data={data}
        margin={{ top: marginTop, right: 12, bottom: marginBottom, left: 12 }}
      >
        <defs>
          <linearGradient id="portfolioLineFade" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--brand-200)" stopOpacity={0} />
            <stop offset="0.15" stopColor="var(--brand-200)" stopOpacity={1} />
            <stop offset="0.85" stopColor="var(--brand-200)" stopOpacity={1} />
            <stop offset="1" stopColor="var(--brand-200)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} horizontalPoints={horizontalPoints} />
        <XAxis dataKey="date" hide />
        <YAxis domain={[paddedMin, paddedMax]} ticks={ticks} hide />
        <ChartTooltip
          content={
            <ChartTooltipContent
              className="w-[150px]"
              nameKey="value"
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
        <Line
          type="monotone"
          dataKey="value"
          stroke="url(#portfolioLineFade)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={true}
        />
      </LineChart>
    </ChartContainer>
  );
}

export { PortfolioLineChart };
