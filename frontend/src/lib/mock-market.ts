import { holdingsData } from "@/lib/mock-portfolio";

export type DateRange = "1D" | "1W" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "10Y";

export const DATE_RANGES: DateRange[] = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "10Y"];

export type MarketDetail = {
  name: string;
  assetCategory: "Stock" | "ETF" | "Index";
  logoColor: string;
  currency: "USD" | "CAD";
  exchange: string;
  currentPrice: number;
  open: number;
  bid: number;
  bidSize: number;
  ask: number;
  askSize: number;
  lastSale: number;
  high: number;
  low: number;
  volume: number;
  avgVolume: number;
  week52High: number;
  week52Low: number;
  marketCap: number;
  sharesOutstanding: number;
  peRatio: number;
  about: string;
  dividend?: {
    frequency: string;
    yieldPct: number;
    exDividendDate: string;
    paymentDate: string;
  };
};

export const mockMarketDetails: Record<string, MarketDetail> = {
  AAPL: {
    name: "Apple",
    assetCategory: "Stock",
    logoColor: "#A2AAAD",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 160,
    open: 158.9,
    bid: 159.85,
    bidSize: 4,
    ask: 160.1,
    askSize: 12,
    lastSale: 160.0,
    high: 161.2,
    low: 157.8,
    volume: 52_300_000,
    avgVolume: 61_800_000,
    week52High: 199.62,
    week52Low: 142.1,
    marketCap: 2_480_000_000_000,
    sharesOutstanding: 15_500_000_000,
    peRatio: 27.4,
    about:
      "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories. It operates through segments including iPhone, Mac, iPad, Wearables, Home and Accessories, and Services. The Services segment includes the App Store, AppleCare, Apple Pay, and subscription offerings such as Apple Music and Apple TV+.",
    dividend: {
      frequency: "Quarterly",
      yieldPct: 0.44,
      exDividendDate: "2026-08-11",
      paymentDate: "2026-08-14",
    },
  },
  GOOGL: {
    name: "Alphabet Inc.",
    assetCategory: "Stock",
    logoColor: "#4285F4",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 2900,
    open: 2875.4,
    bid: 2898.2,
    bidSize: 2,
    ask: 2901.6,
    askSize: 3,
    lastSale: 2900.0,
    high: 2912.75,
    low: 2861.1,
    volume: 1_180_000,
    avgVolume: 1_450_000,
    week52High: 3050.2,
    week52Low: 2410.5,
    marketCap: 1_810_000_000_000,
    sharesOutstanding: 624_000_000,
    peRatio: 24.8,
    about:
      "Alphabet Inc. is the parent company of Google, providing search, advertising, cloud computing, and hardware products. It operates through Google Services, Google Cloud, and Other Bets segments, including Search, YouTube, Android, Chrome, Google Cloud Platform, and early-stage ventures such as Waymo.",
  },
  MSFT: {
    name: "Microsoft Corporation",
    assetCategory: "Stock",
    logoColor: "#00A4EF",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 310,
    open: 307.6,
    bid: 309.7,
    bidSize: 6,
    ask: 310.25,
    askSize: 9,
    lastSale: 310.0,
    high: 311.8,
    low: 306.4,
    volume: 21_400_000,
    avgVolume: 24_900_000,
    week52High: 345.1,
    week52Low: 275.3,
    marketCap: 2_305_000_000_000,
    sharesOutstanding: 7_430_000_000,
    peRatio: 33.6,
    about:
      "Microsoft Corporation develops, licenses, and supports software, services, devices, and solutions. It operates through Productivity and Business Processes (Office, LinkedIn), Intelligent Cloud (Azure, server products), and More Personal Computing (Windows, Xbox, Surface) segments.",
  },
  TSLA: {
    name: "Tesla, Inc.",
    assetCategory: "Stock",
    logoColor: "#CC0000",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 312.45,
    open: 305.1,
    bid: 312.0,
    bidSize: 5,
    ask: 312.9,
    askSize: 8,
    lastSale: 312.45,
    high: 316.4,
    low: 302.75,
    volume: 88_600_000,
    avgVolume: 102_300_000,
    week52High: 410.2,
    week52Low: 178.9,
    marketCap: 998_000_000_000,
    sharesOutstanding: 3_190_000_000,
    peRatio: 68.2,
    about:
      "Tesla, Inc. designs, develops, manufactures, and sells electric vehicles and energy generation and storage systems. It operates through Automotive and Energy Generation and Storage segments, and also develops autonomous-driving software and AI hardware.",
  },
  AMZN: {
    name: "Amazon.com, Inc.",
    assetCategory: "Stock",
    logoColor: "#FF9900",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 195.2,
    open: 192.8,
    bid: 194.9,
    bidSize: 10,
    ask: 195.45,
    askSize: 14,
    lastSale: 195.2,
    high: 196.7,
    low: 191.9,
    volume: 41_200_000,
    avgVolume: 47_600_000,
    week52High: 225.4,
    week52Low: 151.6,
    marketCap: 2_040_000_000_000,
    sharesOutstanding: 10_450_000_000,
    peRatio: 41.7,
    about:
      "Amazon.com, Inc. engages in retail sale of consumer products and subscriptions, and provides cloud computing services through Amazon Web Services. It operates through North America, International, and AWS segments.",
  },
  META: {
    name: "Meta Platforms, Inc.",
    assetCategory: "Stock",
    logoColor: "#0866FF",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 641.1,
    open: 649.3,
    bid: 640.5,
    bidSize: 3,
    ask: 641.8,
    askSize: 5,
    lastSale: 641.1,
    high: 652.9,
    low: 637.2,
    volume: 14_700_000,
    avgVolume: 16_900_000,
    week52High: 738.4,
    week52Low: 453.2,
    marketCap: 1_620_000_000_000,
    sharesOutstanding: 2_530_000_000,
    peRatio: 26.9,
    about:
      "Meta Platforms, Inc. builds technologies that help people connect and share, including Facebook, Instagram, Messenger, and WhatsApp, alongside investments in augmented and virtual reality hardware through Reality Labs.",
  },
  NVDA: {
    name: "NVIDIA",
    assetCategory: "Stock",
    logoColor: "#76B900",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 178.92,
    open: 180.55,
    bid: 178.6,
    bidSize: 20,
    ask: 179.15,
    askSize: 25,
    lastSale: 178.92,
    high: 182.3,
    low: 177.1,
    volume: 142_700_000,
    avgVolume: 168_400_000,
    week52High: 212.4,
    week52Low: 86.6,
    marketCap: 4_360_000_000_000,
    sharesOutstanding: 24_360_000_000,
    peRatio: 52.3,
    about:
      "NVIDIA Corporation designs graphics processing units and system-on-a-chip units for gaming, professional visualization, data center, and automotive markets. Its data-center segment supplies GPUs and networking for AI training and inference workloads.",
  },
  SPY: {
    name: "S&P 500",
    assetCategory: "ETF",
    logoColor: "#1E3A8A",
    currency: "USD",
    exchange: "NYSEARCA",
    currentPrice: 612.47,
    open: 609.8,
    bid: 612.2,
    bidSize: 15,
    ask: 612.75,
    askSize: 18,
    lastSale: 612.47,
    high: 614.9,
    low: 608.1,
    volume: 71_400_000,
    avgVolume: 79_200_000,
    week52High: 640.3,
    week52Low: 510.8,
    marketCap: 610_800_000_000,
    sharesOutstanding: 997_000_000,
    peRatio: 25.1,
    about:
      "SPDR S&P 500 ETF Trust is an exchange-traded fund that tracks the S&P 500 index, providing exposure to 500 of the largest publicly traded companies in the United States across all major sectors.",
  },
  QQQ: {
    name: "Nasdaq 100",
    assetCategory: "ETF",
    logoColor: "#111827",
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: 521.83,
    open: 518.2,
    bid: 521.5,
    bidSize: 11,
    ask: 522.1,
    askSize: 9,
    lastSale: 521.83,
    high: 524.6,
    low: 516.9,
    volume: 38_900_000,
    avgVolume: 43_100_000,
    week52High: 545.8,
    week52Low: 402.1,
    marketCap: 340_200_000_000,
    sharesOutstanding: 652_000_000,
    peRatio: 31.6,
    about:
      "Invesco QQQ Trust is an exchange-traded fund that tracks the Nasdaq-100 Index, composed of the 100 largest non-financial companies listed on the Nasdaq exchange, heavily weighted toward technology.",
  },
  "^GSPC": {
    name: "S&P 500",
    assetCategory: "Index",
    logoColor: "#7C3AED",
    currency: "USD",
    exchange: "INDEX",
    currentPrice: 6187.23,
    open: 6152.1,
    bid: 6186.5,
    bidSize: 1,
    ask: 6187.9,
    askSize: 1,
    lastSale: 6187.23,
    high: 6198.4,
    low: 6141.7,
    volume: 0,
    avgVolume: 0,
    week52High: 6420.5,
    week52Low: 5120.3,
    marketCap: 0,
    sharesOutstanding: 0,
    peRatio: 24.3,
    about:
      "The S&P 500 is a stock market index tracking the performance of 500 of the largest companies listed on U.S. exchanges, widely regarded as one of the best gauges of large-cap U.S. equity performance.",
  },
};

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return hash >>> 0;
}

const FALLBACK_COLORS = ["#B1B3B2", "#97999B", "#76787C", "#53575A"];

/** Any ticker not hand-authored above (e.g. mockTickerDirectory entries) still renders via this. */
export function getMarketDetail(ticker: string): MarketDetail {
  const known = mockMarketDetails[ticker];
  if (known) return known;

  const seed = hashString(ticker);
  const price = 20 + (seed % 480);
  return {
    name: ticker,
    assetCategory: "Stock",
    logoColor: FALLBACK_COLORS[seed % FALLBACK_COLORS.length],
    currency: "USD",
    exchange: "NASDAQ",
    currentPrice: price,
    open: price * 0.99,
    bid: price * 0.999,
    bidSize: 1 + (seed % 20),
    ask: price * 1.001,
    askSize: 1 + ((seed >> 4) % 20),
    lastSale: price,
    high: price * 1.02,
    low: price * 0.98,
    volume: 1_000_000 + (seed % 20_000_000),
    avgVolume: 1_500_000 + (seed % 25_000_000),
    week52High: price * 1.35,
    week52Low: price * 0.65,
    marketCap: price * 1_000_000_000,
    sharesOutstanding: 1_000_000_000,
    peRatio: 15 + (seed % 30),
    about: `${ticker} market and company details aren't tracked in this app's mock dataset yet — placeholder figures shown until real data is wired up.`,
  };
}

// Seeded, deterministic pseudo-random generator (mulberry32) — same ticker+preset
// always produces the same series, unlike Math.random(), so the chart doesn't
// reshuffle on every re-render.
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const SPREAD_BY_PRESET: Record<DateRange, number> = {
  "1D": 0.01,
  "1W": 0.03,
  "1M": 0.08,
  "3M": 0.15,
  "6M": 0.2,
  YTD: 0.2,
  "1Y": 0.3,
  "10Y": 0.6,
};

function isWeekday(d: Date): boolean {
  const day = d.getDay();
  return day !== 0 && day !== 6;
}

/** One point per weekday in [start, now] — matches real trading-day spacing for 1M/3M/6M/YTD/1Y. */
function weekdayDatesBetween(start: Date, end: Date): Date[] {
  const dates: Date[] = [];
  const cur = new Date(start);
  cur.setHours(0, 0, 0, 0);
  while (cur <= end) {
    if (isWeekday(cur)) dates.push(new Date(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return dates;
}

/** The last `count` weekdays up to and including `end`, ascending. */
function lastNWeekdays(end: Date, count: number): Date[] {
  const dates: Date[] = [];
  const cur = new Date(end);
  cur.setHours(0, 0, 0, 0);
  while (dates.length < count) {
    if (isWeekday(cur)) dates.unshift(new Date(cur));
    cur.setDate(cur.getDate() - 1);
  }
  return dates;
}

/** Timestamps every `stepMinutes` from market open (9:30) to close (16:00) on the given day. */
function intradayTimestamps(day: Date, stepMinutes: number): Date[] {
  const start = new Date(day);
  start.setHours(9, 30, 0, 0);
  const end = new Date(day);
  end.setHours(16, 0, 0, 0);
  const timestamps: Date[] = [];
  for (const t = new Date(start); t <= end; t.setMinutes(t.getMinutes() + stepMinutes)) {
    timestamps.push(new Date(t));
  }
  return timestamps;
}

function addMonths(d: Date, months: number): Date {
  const result = new Date(d);
  result.setMonth(result.getMonth() + months);
  return result;
}

/** Point spacing per Wealthsimple's own chart: 5min (1D), 30min (1W), daily (1M–1Y), every 14 days (10Y). */
function getTimestampsForPreset(preset: DateRange, now: Date): Date[] {
  switch (preset) {
    case "1D":
      return intradayTimestamps(now, 5);
    case "1W":
      return lastNWeekdays(now, 5).flatMap((d) => intradayTimestamps(d, 30));
    case "1M":
      return weekdayDatesBetween(addMonths(now, -1), now);
    case "3M":
      return weekdayDatesBetween(addMonths(now, -3), now);
    case "6M":
      return weekdayDatesBetween(addMonths(now, -6), now);
    case "YTD":
      return weekdayDatesBetween(new Date(now.getFullYear(), 0, 1), now);
    case "1Y":
      return weekdayDatesBetween(addMonths(now, -12), now);
    case "10Y": {
      const start = addMonths(now, -120);
      const points: Date[] = [];
      for (const t = new Date(start); t <= now; t.setDate(t.getDate() + 14)) points.push(new Date(t));
      return points;
    }
  }
}

function toDateString(d: Date, includeTime: boolean): string {
  const datePart = d.toISOString().slice(0, 10);
  if (!includeTime) return datePart;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${datePart}T${hh}:${mm}`;
}

/** Brownian-bridge-style mock series: starts at a seeded random price, always ends exactly at `currentPrice`. */
export function generateMockPriceSeries(
  ticker: string,
  currentPrice: number,
  preset: DateRange,
): { date: string; value: number }[] {
  const spread = SPREAD_BY_PRESET[preset];
  const rand = mulberry32(hashString(`${ticker}:${preset}`));
  const now = new Date();
  const timestamps = getTimestampsForPreset(preset, now);
  const n = timestamps.length;
  const includeTime = preset === "1D" || preset === "1W";

  const startPrice = currentPrice * (1 + (rand() * 2 - 1) * spread);

  const rawWalk: number[] = [0];
  for (let i = 1; i < n; i++) {
    rawWalk.push(rawWalk[i - 1] + (rand() * 2 - 1));
  }
  const drift = rawWalk[n - 1];

  return timestamps.map((timestamp, i) => {
    const t = n > 1 ? i / (n - 1) : 1;
    const detrended = rawWalk[i] - t * drift;
    const value = startPrice + (currentPrice - startPrice) * t + detrended * (currentPrice * spread * 0.08);
    return { date: toDateString(timestamp, includeTime), value: Math.max(0.01, value) };
  });
}

export type Activity = {
  id: string;
  transactionDate: string;
  transactionTime: string;
  settlementDate: string;
  settlementTime: string;
  accountId: string;
  accountType: string;
  activityType: "Trade" | "MoneyMovement";
  activitySubType: "MARKET_BUY" | "LIMIT_BUY" | "STOP_LIMIT_BUY" | "STOP_MARKET_BUY" | "RECURRING_BUY";
  direction: "LONG";
  symbol: string;
  name: string;
  currency: "USD" | "CAD";
  quantity: number;
  unitPrice: number;
  fxRate: number | null;
  commission: number;
  netCashAmount: number;
};

const ACTIVITY_TYPE_LABEL: Record<Activity["activitySubType"], string> = {
  MARKET_BUY: "Market buy",
  LIMIT_BUY: "Limit buy",
  STOP_LIMIT_BUY: "Stop limit buy",
  STOP_MARKET_BUY: "Stop market buy",
  RECURRING_BUY: "Recurring buy",
};

export function activityTypeLabel(activity: Activity): string {
  return ACTIVITY_TYPE_LABEL[activity.activitySubType];
}

// Only the 3 held tickers (matches holdingsData) have trade history —
// nothing else in this app's mock data models a real Wealthsimple transaction.
export const mockActivities: Activity[] = [
  {
    id: "act-aapl-1",
    transactionDate: "2024-03-15",
    transactionTime: "04:43",
    settlementDate: "2024-03-18",
    settlementTime: "10:36",
    accountId: "HQ7T3Q2K9CAD",
    accountType: "TFSA",
    activityType: "Trade",
    activitySubType: "LIMIT_BUY",
    direction: "LONG",
    symbol: "AAPL",
    name: "Apple",
    currency: "CAD",
    quantity: 10,
    unitPrice: 150,
    fxRate: 1.36,
    commission: 0,
    netCashAmount: -(10 * 150 * 1.36),
  },
  {
    id: "act-googl-1",
    transactionDate: "2023-11-02",
    transactionTime: "09:47",
    settlementDate: "2023-11-03",
    settlementTime: "13:12",
    accountId: "HQ7T3Q2K9USD",
    accountType: "RRSP",
    activityType: "Trade",
    activitySubType: "MARKET_BUY",
    direction: "LONG",
    symbol: "GOOGL",
    name: "Alphabet Inc.",
    currency: "USD",
    quantity: 5,
    unitPrice: 2800,
    fxRate: null,
    commission: 0,
    netCashAmount: -(5 * 2800),
  },
  {
    id: "act-msft-1",
    transactionDate: "2024-06-20",
    transactionTime: "11:05",
    settlementDate: "2024-06-21",
    settlementTime: "15:52",
    accountId: "HQ7T3Q2K9CAD",
    accountType: "TFSA",
    activityType: "Trade",
    activitySubType: "RECURRING_BUY",
    direction: "LONG",
    symbol: "MSFT",
    name: "Microsoft Corporation",
    currency: "CAD",
    quantity: 8,
    unitPrice: 300,
    fxRate: 1.37,
    commission: 0,
    netCashAmount: -(8 * 300 * 1.37),
  },
];

export function getActivitiesForTicker(ticker: string): Activity[] {
  return mockActivities
    .filter((a) => a.symbol === ticker)
    .sort((a, b) => b.transactionDate.localeCompare(a.transactionDate));
}

export function getPositionForTicker(ticker: string) {
  return holdingsData.find((p) => p.symbol === ticker);
}

export function getTotalPortfolioValue(): number {
  return holdingsData.reduce((sum, p) => sum + p.shares * p.currentPrice, 0);
}
