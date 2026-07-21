import { DotGrid } from "@/components/ui/dot-grid";

const THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60;

interface UptimeMeterProps {
  uptimeSeconds: number;
  cycleSeconds?: number;
  columns?: number;
  rows?: number;
  className?: string;
}

function UptimeMeter({
  uptimeSeconds,
  cycleSeconds = THIRTY_DAYS_SECONDS,
  columns = 10,
  rows = 3,
  className,
}: UptimeMeterProps) {
  const totalDots = columns * rows;
  const progress = (uptimeSeconds % cycleSeconds) / cycleSeconds;
  const filledCount = Math.round(progress * totalDots);

  return (
    <DotGrid
      columns={columns}
      rows={rows}
      filledCount={filledCount}
      filledColor="var(--storage-used)"
      emptyColor="var(--uptime-empty)"
      className={className}
    />
  );
}

export { UptimeMeter };
