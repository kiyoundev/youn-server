export type Position = {
  symbol: string;
  assetType: "Stock" | "ETF";
  shares: number;
  avgPrice: number;
  currentPrice: number;
  purchasedAt: string;
  currency: "USD" | "CAD";
};

export const holdingsData: Position[] = [
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
];

export type StockAlertDirection = "above" | "below";

export type StockAlertData = {
  ticker: string;
  category: "Stock" | "ETF";
  targetPrice: number;
  direction: StockAlertDirection;
  currentPrice: number;
};

export const stockWatchlistData: StockAlertData[] = [
  { ticker: "TSLA", category: "Stock", targetPrice: 300, direction: "above", currentPrice: 312.45 },
  { ticker: "AMZN", category: "Stock", targetPrice: 180, direction: "below", currentPrice: 195.2 },
  { ticker: "META", category: "Stock", targetPrice: 650, direction: "above", currentPrice: 641.1 },
];

/**
 * Stand-in for the future `GET /api/market/search` (Finnhub Symbol Lookup) call —
 * simulates arbitrary-ticker autocomplete until that backend endpoint exists.
 */
export type TickerDirectoryEntry = { symbol: string; name: string };

export const mockTickerDirectory: TickerDirectoryEntry[] = [
  { symbol: "NFLX", name: "Netflix" },
  { symbol: "DIS", name: "Walt Disney" },
  { symbol: "JPM", name: "JPMorgan Chase" },
  { symbol: "BA", name: "Boeing" },
  { symbol: "V", name: "Visa" },
  { symbol: "JNJ", name: "Johnson & Johnson" },
  { symbol: "WMT", name: "Walmart" },
  { symbol: "XOM", name: "Exxon Mobil" },
  { symbol: "SPY", name: "S&P 500 ETF" },
  { symbol: "QQQ", name: "Nasdaq 100 ETF" },
];
