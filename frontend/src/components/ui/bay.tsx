import { cn } from "@/lib/utils"

type BayStatus = "empty" | "healthy" | "warning" | "error"

const dotColor: Record<BayStatus, string> = {
  empty: "var(--status-neutral)",
  healthy: "var(--status-success)",
  warning: "var(--status-warning)",
  error: "var(--status-error)",
}

// only "empty" desaturates the label — healthy/warning/error keep it fixed
const labelColor: Record<BayStatus, string> = {
  empty: "var(--status-neutral)",
  healthy: "var(--foreground)",
  warning: "var(--foreground)",
  error: "var(--foreground)",
}

interface BayProps {
  label: string
  status: BayStatus
  className?: string
}

function Bay({ label, status, className }: BayProps) {
  return (
    <svg
      width="31"
      height="108"
      viewBox="0 0 31 108"
      fill="none"
      className={cn(className)}
      data-slot="bay"
    >
      <rect width="31" height="108" rx="6" fill="var(--secondary)" />
      <text x="15.5" y="15" textAnchor="middle" fontSize="9" fontWeight="600" fill={labelColor[status]}>
        {label}
      </text>
      <rect x="4" y="34" width="23" height="50" rx="4" stroke="var(--border)" />
      <circle cx="15.5" cy="98" r="2" fill={dotColor[status]} />
    </svg>
  )
}

export { Bay }