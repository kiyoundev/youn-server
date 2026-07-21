import { CalendarCog } from "lucide-react";
import { PortfolioLineChart } from "@/components/ui/portfolio-line-chart";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";

interface Position {
  symbol: string;
  assetType: "Stock" | "ETF";
  shares: number;
  avgPrice: number;
  currentPrice: number;
  purchasedAt: string;
  currency: "USD" | "CAD";
}

interface PortfolioTileProps {
  totalValue: number;
  chartData: { date: string; value: number }[];
  positions: Position[];
  onDateRangeClick?: () => void;
  className?: string;
}

const PortfolioTile = ({
  totalValue,
  chartData,
  positions,
  onDateRangeClick,
  className,
}: PortfolioTileProps) => {
  return (
    <Card className={className ?? "w-fit"}>
      <CardHeader>
        <CardTitle className="font-ndot">Portfolio</CardTitle>
      </CardHeader>

      <div className="mx-5 rounded-[12px] bg-muted/50 p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <button onClick={onDateRangeClick} aria-label="Configure date range">
            <CalendarCog
              className="text-brand-200"
              size={20}
              strokeWidth={1.25}
            />
          </button>
          <Label className="text-[18px] font-normal block">
            $
            {totalValue.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </Label>
        </div>
        <PortfolioLineChart data={chartData} />
        <div className="flex items-center justify-between gap-2">
          <Label className="text-[18px] font-normal">Portfolio Value</Label>
          <Badge variant="outline" className="text-[14px] px-3 py-1">
            +9.3%
          </Badge>
        </div>
      </div>

      <div className="mx-5 mb-5 rounded-[12px] bg-muted/50 divide-y divide-[#383939]">
        {positions.map((position) => {
          const changePercent =
            ((position.currentPrice - position.avgPrice) / position.avgPrice) *
            100;
          const changeDollar =
            (position.currentPrice - position.avgPrice) * position.shares;
          const isZero = changePercent === 0;
          const isUp = changePercent > 0;
          const sign = isZero ? "" : isUp ? "+" : "-";
          const changeColor = isZero
            ? "var(--status-neutral)"
            : isUp
              ? "var(--status-success)"
              : "var(--status-error)";
          return (
            <div key={position.symbol} className="flex items-center gap-3 p-3">
              <div className="h-[30px] w-[30px] rounded bg-white" />
              <div className="flex flex-col flex-1 gap-2.5">
                <Label className="text-[14px] font-normal block">
                  {position.symbol}
                </Label>
                <Label className="text-[12px] font-normal text-brand-500 block">
                  {position.shares} Shares ·{" "}
                  {new Date(position.purchasedAt).toLocaleDateString("en-US", {
                    month: "short",
                    year: "numeric",
                  })}
                </Label>
              </div>

              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                {position.assetType}
              </Badge>
              <div className="flex flex-col items-end gap-2.5 min-w-[100px]">
                <Label className="text-[14px] font-normal whitespace-nowrap block">
                  {position.currentPrice.toLocaleString("en-US", {
                    style: "currency",
                    currency: position.currency,
                    currencyDisplay: "code",
                  })}
                </Label>
                <Label
                  className="text-[12px] font-normal whitespace-nowrap block"
                  style={{ color: changeColor }}
                >
                  {sign}
                  {Math.abs(changePercent).toFixed(2)}% ($
                  {Math.abs(changeDollar).toFixed(2)})
                </Label>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

export default PortfolioTile;
