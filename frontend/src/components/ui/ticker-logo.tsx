"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

const LOGO_BASE = "https://logos.wealthsimple.com";

// Wealthsimple names logos {ticker}-{exchange}.png and the ledger carries no
// exchange, so try the likely ones in order: TSX for CAD, Nasdaq then NYSE for USD.
function logoUrls(symbol: string, currency: "USD" | "CAD") {
  const ticker = symbol.replace(/\.(TO|V|NE|CN)$/i, "").toLowerCase();
  const exchanges = currency === "CAD" ? ["xtse"] : ["xnas", "xnys"];
  return exchanges.map((x) => `${LOGO_BASE}/${encodeURIComponent(ticker)}-${x}.png`);
}

export function TickerLogo({ symbol, currency }: { symbol: string; currency: "USD" | "CAD" }) {
  const [attempt, setAttempt] = useState(0); // index of the URL being tried
  const urls = logoUrls(symbol, currency);
  const box = "h-[30px] w-[30px] shrink-0 self-center rounded bg-white";

  // Every URL failed: a plain white box with the full ticker.
  if (attempt >= urls.length) {
    return (
      <div
        className={cn(
          box,
          "flex items-center justify-center overflow-hidden font-semibold leading-none text-black",
          symbol.length > 4 ? "text-[7px]" : "text-[9px]",
        )}
      >
        {symbol}
      </div>
    );
  }
  return (
    // Plain <img>: an unauthenticated external asset; next/image would need a remotePatterns entry.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={urls[attempt]}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setAttempt((a) => a + 1)}
      className={cn(box, "object-contain")}
    />
  );
}
