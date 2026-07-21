import { cn } from "@/lib/utils";

const DOT_R = 5.25;
const PITCH = 12.5;

interface DotGridProps {
  columns: number;
  rows: number;
  filledCount: number;
  filledColor: string;
  emptyColor: string;
  className?: string;
}

function DotGrid({
  columns,
  rows,
  filledCount,
  filledColor,
  emptyColor,
  className,
}: DotGridProps) {
  const width = columns * PITCH - (PITCH - DOT_R * 2);
  const height = rows * PITCH - (PITCH - DOT_R * 2);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className={cn(className)}
      data-slot="dot-grid"
    >
      {Array.from({ length: rows }).map((_, rowIndex) =>
        Array.from({ length: columns }).map((_, colIndex) => {
          const dotIndex = rowIndex * columns + colIndex;
          return (
            <circle
              key={`${rowIndex}-${colIndex}`}
              cx={colIndex * PITCH + DOT_R}
              cy={rowIndex * PITCH + DOT_R}
              r={DOT_R}
              fill={dotIndex < filledCount ? filledColor : emptyColor}
            />
          );
        }),
      )}
    </svg>
  );
}

export { DotGrid };
