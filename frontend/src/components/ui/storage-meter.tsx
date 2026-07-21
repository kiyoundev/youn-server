import { cn } from "@/lib/utils"

const CELL = 4
const GAP = 4
const PITCH = CELL + GAP

interface StorageMeterProps {
  available: number
  used: number
  reserved: number
  columns?: number
  rows?: number
  className?: string
}

function StorageMeter({
  available,
  used,
  reserved,
  columns = 29,
  rows = 4,
  className,
}: StorageMeterProps) {
  const total = available + used + reserved
  const totalCells = columns * rows

  const availableCells =
    total > 0 ? Math.round((available / total) * totalCells) : totalCells
  const usedCells = total > 0 ? Math.round((used / total) * totalCells) : 0
  const reservedCells = Math.max(0, totalCells - availableCells - usedCells)

  const cellColors: string[] = [
    ...Array(availableCells).fill("var(--storage-available)"),
    ...Array(usedCells).fill("var(--storage-used)"),
    ...Array(reservedCells).fill("var(--storage-reserved)"),
  ].slice(0, totalCells)

  const width = columns * PITCH - GAP
  const height = rows * PITCH - GAP

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className={cn(className)}
      data-slot="storage-meter"
    >
      {Array.from({ length: columns }).map((_, colIndex) =>
        Array.from({ length: rows }).map((_, rowIndex) => (
          <rect
            key={`${colIndex}-${rowIndex}`}
            x={colIndex * PITCH}
            y={rowIndex * PITCH}
            width={CELL}
            height={CELL}
            rx="0.5"
            fill={cellColors[colIndex * rows + rowIndex]}
          />
        ))
      )}
    </svg>
  )
}

export { StorageMeter }
