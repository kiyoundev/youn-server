"use client";

import { Cell, Pie, PieChart } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";

interface AllocationSlice {
  category: string;
  value: number;
  /** Overrides the chart-level `thickness` for this slice only. */
  thickness?: number;
}

interface AllocationDonutChartProps {
  data: AllocationSlice[];
  height?: number;
  className?: string;
  /** Ring thickness as a percentage of the outer radius (0–100). */
  thickness?: number;
  /** Corner rounding on each slice's arc ends. */
  cornerRadius?: number;
  /** Gap between adjacent slices, in degrees. */
  gapAngle?: number;
}

// Same reasoning as product-price-chart.tsx's seriesKey — CSS custom-property
// names can't safely contain arbitrary characters, so the config/CSS-facing
// key stays separate from the category name used for display.
const categoryKey = (category: string) => category.replace(/[^a-zA-Z0-9_-]/g, "_");

function AllocationDonutChart({ data, height = 150, className, thickness = 20, cornerRadius = 100, gapAngle = 6 }: AllocationDonutChartProps) {
  const chartConfig = data.reduce((config, slice, i) => {
    config[categoryKey(slice.category)] = {
      label: slice.category,
      color: `var(--chart-${(i % 5) + 1})`,
    };
    return config;
  }, {} as ChartConfig);

  // Recharts' <Pie> only accepts one shared inner/outer radius for every
  // slice it renders — there's no per-Cell radius override. To vary
  // thickness per slice, render one <Pie> pass per distinct thickness,
  // each using the FULL data array (so angle proportions/positions stay
  // identical across passes) but only that pass's own slices get a real
  // color; every other slice is invisible (transparent + pointer-events
  // none, so it can't steal hover from the real slice under/over it).
  const thicknessTiers = Array.from(new Set(data.map((slice) => slice.thickness ?? thickness)));

  return (
    <ChartContainer config={chartConfig} className={className} style={{ height, width: "100%" }}>
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent hideLabel />} />
        {thicknessTiers.map((tier) => (
          <Pie
            key={tier}
            data={data}
            dataKey="value"
            nameKey="category"
            innerRadius={`${100 - tier}%`}
            outerRadius="100%"
            cornerRadius={cornerRadius}
            paddingAngle={gapAngle}
            strokeWidth={0}
            isAnimationActive={false}
          >
            {data.map((slice) => {
              const belongsToTier = (slice.thickness ?? thickness) === tier;
              return (
                <Cell
                  key={slice.category}
                  fill={belongsToTier ? `var(--color-${categoryKey(slice.category)})` : "transparent"}
                  style={belongsToTier ? undefined : { pointerEvents: "none" }}
                />
              );
            })}
          </Pie>
        ))}
      </PieChart>
    </ChartContainer>
  );
}

export { AllocationDonutChart };
