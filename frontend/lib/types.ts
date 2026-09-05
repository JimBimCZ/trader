/**
 * How a panel's first load went.
 *
 * Three states, because two produced a bug in each direction: a boolean that
 * only ever flipped on success left a failed fetch showing a skeleton for
 * ever, and a boolean flipped in a `finally` made the panel claim the data
 * was empty when nobody had managed to read it. "We asked and it did not
 * work" is its own answer and has to be rendered as one.
 */
export type LoadState = "pending" | "ready" | "failed";

/**
 * Wire types, mirroring planning/API_CONTRACT.md.
 *
 * Raw* types are exactly what the backend sends (snake_case). The camelCase
 * types are what the app uses internally, converted at the parse boundary.
 */

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

export interface RawTradeReceipt {
  trade: {
    id: string;
    ticker: string;
    side: "buy" | "sell";
    quantity: number;
    price: number;
    executed_at: string;
  };
  cash_balance: number;
  position: { ticker: string; quantity: number; avg_cost: number } | null;
  realized_pnl: number | null;
  total_value: number;
}

/**
 * What a fill actually was, flattened from the response.
 *
 * Distinct from `Portfolio`, which says what the account holds *now*: this
 * says what the user just did, and stays true even when the re-reads that
 * follow the trade fail.
 */
export interface TradeReceipt {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  /** The fill price -- the cached quote read once immediately before execution. */
  price: number;
  executedAt: string;
  cashBalance: number;
  /** null when a sell closed the position entirely. */
  position: { quantity: number; avgCost: number } | null;
  /** Populated on sells, null on buys. Computed by the server, never stored. */
  realizedPnl: number | null;
  totalValue: number;
}

export interface SnapshotPoint {
  totalValue: number;
  recordedAt: string;
}

/** One executed fill, as the history view renders it. */
export interface TradeRecord {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executedAt: string;
  /** quantity × price, rounded server-side so the column always adds up. */
  value: number;
  /** Null on every buy — a buy realizes nothing, and 0 would read as
   *  "broke even". The table prints an em dash for it. */
  realizedPnl: number | null;
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

export interface Session {
  id: string;
  kind: "guest" | "user";
  email: string | null;
  name: string | null;
  avatar: string | null;
  /** Whether signing in would discard anything. Drives the guest hint copy. */
  hasActivity: boolean;
}

export interface AuthProvider {
  name: string;
  label: string;
}
