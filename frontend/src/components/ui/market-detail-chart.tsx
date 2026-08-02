"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, XAxis, YAxis, type MouseHandlerDataParam } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";

export interface ChartPoint {
  date: string;
  value: number;
}

interface MarketDetailChartProps {
  data: ChartPoint[];
  /** Most recent buy tranche's price — dashed reference line, only passed when a Position exists for this ticker. Also the up/down threshold for the line color. */
  avgCost?: number;
  /** Date the reference-price line marks — draws the vertical marker + dot alongside it. */
  avgCostDate?: string;
  isPositive: boolean;
  height?: number;
  className?: string;
  /** Fires with the hovered point (or null on mouse-leave) so the page can update the price/change header. */
  onHoverChange?: (point: ChartPoint | null) => void;
}

const SUCCESS = "var(--status-success)";
const ERROR = "var(--status-error)";

const chartConfig = {
  value: { label: "Price" },
} satisfies ChartConfig;

interface ReferencePriceLabelProps {
  viewBox?: { x: number; y: number; width: number; height: number };
  value: number;
}

function ReferencePriceLabel({ viewBox, value }: ReferencePriceLabelProps) {
  if (!viewBox) return null;
  const text = `$${value.toFixed(2)}`;
  const width = text.length * 6.5 + 12;
  const height = 18;
  const x = viewBox.x + viewBox.width - width / 2;
  const y = viewBox.y - height / 2;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={height / 2} fill="var(--popover)" stroke="var(--border)" strokeWidth={1} />
      <text x={x + width / 2} y={y + height / 2 + 4} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">
        {text}
      </text>
    </g>
  );
}

/** "Jul 31, 2026 12:05 PM ET" for intraday points, "Jul 31, 2026" for daily+ points. */
function formatHoverLabel(dateStr: string): string {
  const hasTime = dateStr.includes("T");
  const d = new Date(hasTime ? dateStr : `${dateStr}T00:00:00`);
  const datePart = d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  if (!hasTime) return datePart;
  const timePart = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${datePart} ${timePart} ET`;
}

function MarketDetailChart({ data, avgCost, avgCostDate, isPositive, height = 260, className, onHoverChange }: MarketDetailChartProps) {
  const statusVar = isPositive ? SUCCESS : ERROR;
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    onHoverChange?.(hoverIndex !== null ? (data[hoverIndex] ?? null) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoverIndex]);

  const values = data.map((d) => d.value);
  if (avgCost !== undefined) values.push(avgCost);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const paddedMin = rawMin - (rawMin > 0 ? rawMin * 0.03 : 0);
  const paddedMax = rawMax + rawMax * 0.03;
  const tickCount = 5;
  const ticks = Array.from({ length: tickCount }, (_, i) => paddedMin + ((paddedMax - paddedMin) * i) / (tickCount - 1));

  const marginTop = 24;
  const marginBottom = 4;
  const plotHeight = height - marginTop - marginBottom;
  const horizontalPoints = Array.from({ length: tickCount }, (_, i) => marginTop + (plotHeight * i) / (tickCount - 1));

  const colorAt = (value: number) => (avgCost !== undefined ? (value >= avgCost ? SUCCESS : ERROR) : statusVar);

  const avgCostPoint = avgCostDate ? data.find((d) => d.date === avgCostDate) : undefined;
  const hoverPoint = hoverIndex !== null ? data[hoverIndex] : undefined;
  // Whole line is one solid color — driven by the hovered point vs. the threshold,
  // falling back to the last (current) point when not hovering.
  const activePoint = hoverPoint ?? data[data.length - 1];
  const lineColor = activePoint ? colorAt(activePoint.value) : statusVar;
  const hoverFraction = hoverIndex !== null && data.length > 1 ? hoverIndex / (data.length - 1) : null;
  const gradientId = "marketDetailHoverGradient";

  return (
    <ChartContainer config={chartConfig} className={className} style={{ height, width: "100%" }} data-slot="market-detail-chart">
      <LineChart
        data={data}
        margin={{ top: marginTop, right: avgCost !== undefined ? 56 : 12, bottom: marginBottom, left: 12 }}
        onMouseMove={(state: MouseHandlerDataParam) => {
          if (state?.isTooltipActive && state.activeTooltipIndex !== null && state.activeTooltipIndex !== undefined) {
            const index = Number(state.activeTooltipIndex);
            if (!Number.isNaN(index)) setHoverIndex(index);
          }
        }}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {hoverFraction !== null && (
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
              <stop offset={hoverFraction} stopColor={lineColor} stopOpacity={1} />
              <stop offset={hoverFraction} stopColor={lineColor} stopOpacity={0.35} />
            </linearGradient>
          </defs>
        )}
        <CartesianGrid vertical={false} horizontalPoints={horizontalPoints} />
        <XAxis dataKey="date" hide />
        <YAxis domain={[paddedMin, paddedMax]} ticks={ticks} hide />
        {avgCost !== undefined && (
          <ReferenceLine
            y={avgCost}
            stroke="var(--muted-foreground)"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={<ReferencePriceLabel value={avgCost} />}
          />
        )}
        {avgCostPoint && <ReferenceLine x={avgCostPoint.date} stroke="var(--muted-foreground)" strokeWidth={1} />}
        {avgCostPoint && <ReferenceDot x={avgCostPoint.date} y={avgCostPoint.value} r={4} fill={colorAt(avgCostPoint.value)} stroke="none" />}
        {hoverPoint && (
          <ReferenceLine
            x={hoverPoint.date}
            stroke="var(--muted-foreground)"
            strokeWidth={1}
            label={{ value: formatHoverLabel(hoverPoint.date), position: "top", fill: "var(--foreground)", fontSize: 12 }}
          />
        )}
        {hoverPoint && <ReferenceDot x={hoverPoint.date} y={hoverPoint.value} r={4} fill={colorAt(hoverPoint.value)} stroke="none" />}
        <ChartTooltip content={() => null} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={hoverFraction !== null ? `url(#${gradientId})` : lineColor}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  );
}

export { MarketDetailChart };
