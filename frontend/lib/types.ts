/**
 * Wire types, mirroring planning/API_CONTRACT.md.
 *
 * Raw* types are exactly what the backend sends (snake_case). The camelCase
 * types are what the app uses internally, converted at the parse boundary.
 */

/** One ticker's entry in an SSE frame. */
export interface RawPriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number;
  session_open: number;
  change: number;
  change_percent: number;
  daily_change: number;
  daily_change_percent: number;
  direction: "up" | "down" | "flat";
}

/** An SSE frame: every tracked ticker, keyed by symbol. */
export type PriceFrame = Record<string, RawPriceUpdate>;

export interface PriceSnapshot {
  ticker: string;
  price: number;
  previousPrice: number;
  sessionOpen: number;
  timestamp: number;
  /** Movement since the session baseline. The number labelled "daily change". */
  dailyChangePercent: number;
  /** Tick-over-tick direction. Drives the flash only. */
  direction: "up" | "down" | "flat";
}

export interface RawPosition {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pct_change: number;
}

export interface Position {
  ticker: string;
  quantity: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  /** Return since acquisition, not the daily change. */
  pctChange: number;
}

export interface Portfolio {
  cashBalance: number;
  positions: Position[];
  positionsValue: number;
  totalValue: number;
  unrealizedPnl: number;
}

export interface SnapshotPoint {
  totalValue: number;
  recordedAt: string;
}

export interface HistoryPoint {
  timestamp: number;
  price: number;
}

export interface ExecutedAction {
  kind: "trade" | "watchlist";
  ticker: string;
  status: "ok" | "error";
  detail: Record<string, unknown>;
  errorCode: string | null;
  errorMessage: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions: ExecutedAction[] | null;
  createdAt: string;
}

export interface ChatReply {
  message: string;
  actions: ExecutedAction[];
  error: boolean;
}

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";
