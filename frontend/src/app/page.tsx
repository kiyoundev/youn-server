"use client";

import useSWR from "swr";
import { POLL_INTERVAL_MS } from "@/lib/polling";
import StorageTile from "@/components/tiles/storage-tile";
import type { BayStatus } from "@/components/ui/bay";
import UptimeTile from "@/components/tiles/uptime-tile";
import CpuTile from "@/components/tiles/cpu-tile";
import MemoryTile from "@/components/tiles/memory-tile";
import PortfolioTile from "@/components/tiles/portfolio-tile";
import GitUpdateTile from "@/components/tiles/git-update-tile";
import SystemRestartTile from "@/components/tiles/system-restart-tile";
import DockerTile from "@/components/tiles/docker-tile";
import ServicesTile from "@/components/tiles/services-tile";
import WatchlistTile from "@/components/tiles/watchlist-tile";
import DateTile from "@/components/tiles/date-tile";
import { LoadingScreen } from "@/components/ui/loading-screen";

interface StorageData {
  bays: { label: string; status: BayStatus }[];
  available: number;
  used: number;
  reserved: number;
}

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function Home() {
  const { data, error, isLoading } = useSWR<StorageData>("/api/proxy/system/storage", fetcher, { refreshInterval: POLL_INTERVAL_MS });

  return (
    <main className="flex min-h-screen flex-col items-center gap-4">
      {isLoading && <LoadingScreen page="Home" />}
      {error && <p>Failed to load storage data</p>}
      {data && (
        <div className="grid grid-cols-[clamp(354px,25vw,372px)_1fr] gap-5 p-5 w-full">
          {/* left column */}
          <div className="flex flex-col gap-5 w-full">
            <DateTile className="flex-1" />
            <div className="flex gap-5 w-full">
              <CpuTile percent={50} tempC={64} className="min-w-[152px] flex-1 h-[165px]" />
              <MemoryTile percent={75} totalGb={8} className="min-w-[152px] flex-1 h-[165px]" />
            </div>
            <StorageTile bays={data.bays} available={data.available} used={data.used} reserved={data.reserved} className="w-full" />
            <div className="flex gap-5 w-full">
              <DockerTile name="Frontend" status="running" port={3000} className="min-w-[167px] w-[176px] h-[191.5px]" />
              <DockerTile name="Backend" status="running" port={8000} className="min-w-[167px] w-[176px] h-[191.5px]" />
            </div>
            <div className="flex gap-5 w-full">
              <GitUpdateTile name="TradingAgents" commitsBehind={3} className="min-w-[167px] w-[176px] h-[191.5px]" />
              <GitUpdateTile name="Server" commitsBehind={0} className="min-w-[167px] w-[176px] h-[191.5px]" />
            </div>
            <div className="flex gap-5 w-full">
              <UptimeTile uptimeSeconds={223456} className="min-w-[167px] w-[176px] h-full" />
              <SystemRestartTile className="min-w-[167px] w-[176px] aspect-square" />
            </div>
          </div>
          {/* right column */}
          <div className="flex flex-col gap-5 min-w-0">
            <ServicesTile />
            <div className="flex gap-5 w-full flex-1">
              <div className="flex-1 min-w-0">
                <PortfolioTile
                  totalValue={100000}
                  chartData={[
                    { date: "2025-10-13", value: 95000 },
                    { date: "2025-10-14", value: 99000 },
                    { date: "2025-10-15", value: 96500 },
                    { date: "2025-10-16", value: 101000 },
                    { date: "2025-10-17", value: 98000 },
                    { date: "2025-10-18", value: 103000 },
                    { date: "2025-10-19", value: 100500 },
                    { date: "2025-10-20", value: 106000 },
                    { date: "2025-10-21", value: 102000 },
                    { date: "2025-10-22", value: 108000 },
                  ]}
                  positions={[
                    {
                      symbol: "AAPL",
                      assetType: "Stock",
                      shares: 10,
                      avgPrice: 150,
                      currentPrice: 160,
                      purchasedAt: "2024-03-15",
                      currency: "USD",
                    },
                    {
                      symbol: "GOOGL",
                      assetType: "Stock",
                      shares: 5,
                      avgPrice: 2800,
                      currentPrice: 2900,
                      purchasedAt: "2023-11-02",
                      currency: "USD",
                    },
                    {
                      symbol: "MSFT",
                      assetType: "Stock",
                      shares: 8,
                      avgPrice: 300,
                      currentPrice: 310,
                      purchasedAt: "2024-06-20",
                      currency: "USD",
                    },
                  ]}
                  className="w-full h-full"
                />
              </div>
              <div className="flex-1 min-w-0">
                <WatchlistTile
                  items={[
                    {
                      id: "airpods-max-2",
                      name: "Apple Airpod Max 2",
                      bestPrice: 549.99,
                      targetPrice: 500,
                      alertState: "armed",
                      retailers: [
                        {
                          name: "Amazon.ca",
                          price: 549.99,
                          inStock: true,
                          url: "https://www.amazon.ca",
                        },
                        {
                          name: "Best Buy",
                          price: 559.99,
                          inStock: true,
                          url: "https://www.bestbuy.ca",
                        },
                      ],
                    },
                    {
                      id: "uniqlo-geared-shorts",
                      name: "Uniqlo Geared Shorts",
                      bestPrice: 39.9,
                      targetPrice: 30,
                      alertState: "armed",
                      retailers: [
                        {
                          name: "Uniqlo.com",
                          price: 39.9,
                          inStock: true,
                          url: "https://www.uniqlo.com",
                        },
                      ],
                    },
                  ]}
                  className="w-full h-full"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
