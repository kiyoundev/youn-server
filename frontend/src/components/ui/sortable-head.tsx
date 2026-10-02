import { MoveDown, MoveUp, MoveVertical } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import type { SortDir } from "@/lib/watchlist-sort";

interface SortableHeadProps {
  label: string;
  // null when this column isn't the active sort.
  direction: SortDir | null;
  onSort: () => void;
}

// Issue #56 — a clickable column header. Active column shows its direction;
// inactive ones show a faint up/down hint.
function SortableHead({ label, direction, onSort }: SortableHeadProps) {
  const Icon = direction === "asc" ? MoveUp : direction === "desc" ? MoveDown : MoveVertical;
  return (
    <TableHead aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}>
      <button type="button" onClick={onSort} className="inline-flex cursor-pointer items-center gap-1 hover:text-foreground">
        {label}
        <Icon className={direction ? "size-3.5" : "size-3.5 text-muted-foreground/50"} />
      </button>
    </TableHead>
  );
}

export { SortableHead };
