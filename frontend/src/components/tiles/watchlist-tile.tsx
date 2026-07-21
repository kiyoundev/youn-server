"use client";

import { useState } from "react";
import { Plus, ChevronDown, ChevronUp } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardAction } from "@/components/ui/card";

type AlertState = "armed" | "triggered" | "dismissed";

interface Retailer {
  name: string;
  price: number;
  inStock: boolean;
  url: string;
}

interface WatchlistItem {
  id: string;
  name: string;
  bestPrice: number;
  targetPrice: number;
  alertState: AlertState;
  retailers: Retailer[];
}

interface WatchlistTileProps {
  items: WatchlistItem[];
  onAdd?: () => void;
  className?: string;
}

const WatchlistTile = ({ items, onAdd, className }: WatchlistTileProps) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <Card className={className ?? "w-full"}>
      <CardHeader>
        <CardTitle className="font-ndot">Watchlist</CardTitle>
        <CardAction>
          <button onClick={onAdd} aria-label="Add item">
            <Plus className="text-brand-200" size={20} strokeWidth={1.25} />
          </button>
        </CardAction>
      </CardHeader>

      <div className="mx-5 mb-5 rounded-[12px] bg-muted/50 divide-y divide-[#383939]">
        {items.map((item) => {
          const isExpanded = expandedId === item.id;
          return (
            <div key={item.id}>
              <button
                onClick={() => setExpandedId(isExpanded ? null : item.id)}
                className="flex w-full items-center gap-3 p-3 text-left"
              >
                <div className="flex flex-col gap-2.5 flex-1">
                  <Label className="text-[14px] font-normal block">
                    {item.name}
                  </Label>
                  <Label className="text-[12px] font-normal text-brand-500 block">
                    Target ${item.targetPrice.toFixed(2)}
                  </Label>
                </div>
                <Label className="text-[14px] font-normal block">
                  ${item.bestPrice.toFixed(2)}
                </Label>
                {isExpanded ? (
                  <ChevronUp
                    className="text-brand-300 shrink-0"
                    size={16}
                    strokeWidth={1.25}
                  />
                ) : (
                  <ChevronDown
                    className="text-brand-300 shrink-0"
                    size={16}
                    strokeWidth={1.25}
                  />
                )}
              </button>
              {isExpanded && (
                <div className="flex flex-col gap-2 px-3 pb-3">
                  {item.retailers.map((retailer) => (
                    <a
                      key={retailer.name}
                      href={retailer.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-3 rounded bg-[oklab(1_0_0/0.045)] p-2"
                    >
                      <Label className="text-[12px] font-normal flex-1">
                        {retailer.name}
                      </Label>
                      <Label className="text-[12px] font-normal text-brand-300">
                        {retailer.inStock ? "In Stock" : "Out of Stock"}
                      </Label>
                      <Label className="text-[12px] font-normal">
                        ${retailer.price.toFixed(2)}
                      </Label>
                    </a>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
};

export default WatchlistTile;
