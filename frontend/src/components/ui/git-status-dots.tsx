import { DotGrid } from "@/components/ui/dot-grid";

const TOTAL_DOTS = 10;

interface GitStatusDotsProps {
  commitsBehind: number;
  className?: string;
}

function GitStatusDots({ commitsBehind, className }: GitStatusDotsProps) {
  const behindCount = Math.min(Math.max(commitsBehind, 0), TOTAL_DOTS);
  const caughtUpCount = TOTAL_DOTS - behindCount;

  return (
    <DotGrid
      columns={TOTAL_DOTS}
      rows={1}
      filledCount={caughtUpCount}
      filledColor="var(--storage-used)"
      emptyColor="var(--brand-200)"
      className={className}
    />
  );
}

export { GitStatusDots };
