import { cn } from "@/lib/utils";

type ServiceStatus = "healthy" | "degraded" | "down";

const STATUS_COLOR: Record<ServiceStatus, string> = {
  healthy: "var(--status-success)",
  degraded: "var(--status-warning)",
  down: "var(--status-error)",
};

interface StatusDotProps {
  status: ServiceStatus;
  className?: string;
}

function StatusDot({ status, className }: StatusDotProps) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        status === "healthy" && "animate-dot-pulse",
        className,
      )}
      style={{ backgroundColor: STATUS_COLOR[status] }}
      data-slot="status-dot"
    />
  );
}

export { StatusDot };
export type { ServiceStatus };
