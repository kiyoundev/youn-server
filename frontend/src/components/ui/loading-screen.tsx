import * as React from "react"
import { LoaderIcon } from "lucide-react"

import { cn } from "@/lib/utils"

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <LoaderIcon
      role="status"
      aria-label="Loading"
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  )
}

interface LoadingScreenProps {
  // e.g. "Watchlist" — rendered as "Loading Watchlist Page"
  page: string
}

function LoadingScreen({ page }: LoadingScreenProps) {
  return (
    <div
      data-slot="loading-screen"
      className="flex min-h-screen w-full flex-col items-center justify-center gap-3"
    >
      <Spinner className="size-6" />
      <span className="text-sm text-muted-foreground">Loading {page} Page</span>
    </div>
  )
}

export { Spinner, LoadingScreen }
