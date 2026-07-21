"use client";

import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";
import { cn } from "@/lib/utils";

interface RadialGaugeProps {
  percent: number;
  label: string;
  size?: number;
  className?: string;
}

function RadialGauge({
  percent,
  label,
  size = 100,
  className,
}: RadialGaugeProps) {
  const data = [{ value: percent, fill: "var(--storage-used)" }];

  return (
    <div
      className={cn("relative", className)}
      style={{ width: size, height: size }}
    >
      <RadialBarChart
        width={size}
        height={size}
        cx="50%"
        cy="50%"
        innerRadius="70%"
        outerRadius="100%"
        barSize={8}
        data={data}
        startAngle={-135}
        endAngle={-405}
        margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
        data-slot="radial-gauge"
      >
        <PolarAngleAxis
          type="number"
          domain={[0, 100]}
          angleAxisId={0}
          tick={false}
        />
        <RadialBar
          background={{ fill: "var(--uptime-empty)" }}
          dataKey="value"
          cornerRadius={999}
        />
      </RadialBarChart>
      <div className="absolute inset-0 flex items-center justify-center text-brand-100">
        <span className="flex items-baseline">
          <span className="text-[22px] font-normal">{percent}</span>
          <span className="text-[14px]">%</span>
        </span>
      </div>
      <div className="absolute bottom-1 left-0 right-0 flex justify-center text-[14px] font-normal text-brand-300">
        {label}
      </div>
    </div>
  );
}

export { RadialGauge };
