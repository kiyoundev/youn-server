"use client";

import { useMemo, useRef, useState, type ChangeEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search, Upload } from "lucide-react";
import { Command as CommandPrimitive } from "cmdk";
import { cn } from "@/lib/utils";
import { Command, CommandList, CommandEmpty, CommandGroup, CommandItem } from "@/components/ui/command";
import { holdingsData, stockWatchlistData, mockTickerDirectory } from "@/lib/mock-portfolio";
import { useNavSlotRegistration } from "@/components/nav-slot";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/watchlist", label: "Watchlist" },
];

// Routes that render their own search + action controls into the nav via
// the portal slot, replacing the default ticker search + Upload button.
// Add a route here once its page has been migrated to useNavSlot().
const NAV_SLOT_ROUTES = ["/watchlist"];

const Nav = () => {
  const pathname = usePathname();
  const router = useRouter();
  const registerSlot = useNavSlotRegistration();
  const usesNavSlot = NAV_SLOT_ROUTES.includes(pathname);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [csvFileName, setCsvFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  const trackedTickers = useMemo(() => {
    const tickers = [...holdingsData.map((p) => p.symbol), ...stockWatchlistData.map((a) => a.ticker)];
    return Array.from(new Set(tickers));
  }, []);

  const searchResults = useMemo(() => mockTickerDirectory.filter((entry) => !trackedTickers.includes(entry.symbol)), [trackedTickers]);

  const handleSelect = (ticker: string) => {
    router.push(`/market/${encodeURIComponent(ticker)}`);
    setQuery("");
    setOpen(false);
    setExpanded(false);
  };

  const handleExpand = () => {
    setExpanded(true);
    setOpen(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const handleBlur = () => {
    setTimeout(() => {
      setOpen(false);
      if (!query) setExpanded(false);
    }, 150);
  };

  const handleCsvSelect = (e: ChangeEvent<HTMLInputElement>) => {
    setCsvFileName(e.target.files?.[0]?.name ?? null);
    e.target.value = "";
  };

  return (
    <nav className="flex items-center justify-between gap-4 px-5 pt-5">
      <div className="flex gap-1">
        {NAV_LINKS.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                isActive ? "bg-secondary text-secondary-foreground" : "text-brand-300 hover:bg-muted hover:text-foreground",
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
      <div className="flex items-center gap-1">
        {usesNavSlot ? (
          <div ref={registerSlot} className="flex items-center gap-1" />
        ) : (
          <>
            <Command className="relative w-fit shrink-0 overflow-visible rounded-lg bg-transparent p-0" shouldFilter>
              <div
                className={cn(
                  "flex h-8 items-center overflow-hidden rounded-lg border transition-[width,background-color,border-color] duration-300 ease-in-out",
                  expanded ? "w-[260px] border-input/30 bg-input/30" : "w-8 border-transparent bg-transparent",
                )}
              >
                <button
                  type="button"
                  aria-label="Open ticker search"
                  className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
                  onClick={handleExpand}
                  tabIndex={expanded ? -1 : 0}
                >
                  <Search className="size-4 shrink-0 opacity-50" />
                </button>
                <CommandPrimitive.Input
                  ref={inputRef}
                  value={query}
                  onValueChange={setQuery}
                  onFocus={() => setOpen(true)}
                  onBlur={handleBlur}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      setQuery("");
                      setOpen(false);
                      setExpanded(false);
                      inputRef.current?.blur();
                    }
                  }}
                  placeholder="Search Ticker..."
                  aria-label="Search Ticker"
                  className={cn(
                    "h-full min-w-0 bg-transparent text-sm outline-hidden transition-opacity duration-200 disabled:cursor-not-allowed disabled:opacity-50",
                    expanded ? "w-full pr-2 opacity-100 delay-100" : "w-0 opacity-0",
                  )}
                />
              </div>
              {open && expanded && query && (
                <CommandList className="absolute inset-x-0 top-full z-50 mt-1 max-h-80 rounded-lg bg-popover p-1 ring-1 ring-foreground/10 shadow-md">
                  <CommandEmpty>No tickers found.</CommandEmpty>
                  {trackedTickers.length > 0 && (
                    <CommandGroup heading="Holdings & Watchlist">
                      {trackedTickers.map((ticker) => (
                        <CommandItem key={ticker} value={ticker} onSelect={() => handleSelect(ticker)}>
                          {ticker}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  )}
                  <CommandGroup heading="Search Results">
                    {searchResults.map((entry) => (
                      <CommandItem key={entry.symbol} value={`${entry.symbol} ${entry.name}`} onSelect={() => handleSelect(entry.symbol)}>
                        <span className="font-medium">{entry.symbol}</span>
                        <span className="text-muted-foreground">{entry.name}</span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              )}
            </Command>
            {csvFileName && <span className="text-muted-foreground max-w-[140px] truncate text-xs">{csvFileName}</span>}
            <button
              type="button"
              aria-label="Upload Wealthsimple CSV"
              className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-muted"
              onClick={() => csvInputRef.current?.click()}
            >
              <Upload className="size-4 shrink-0 opacity-50" />
            </button>
            <input ref={csvInputRef} type="file" accept=".csv" className="hidden" onChange={handleCsvSelect} />
          </>
        )}
      </div>
    </nav>
  );
};

export default Nav;
