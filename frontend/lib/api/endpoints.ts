import { api, CHAT_TIMEOUT_MS } from "./client";
import type {
  AuthProvider,
  ChatMessage,
  ChatReply,
  ExecutedAction,
  HistoryPoint,
  Portfolio,
  Position,
  RawPosition,
  RawTradeReceipt,
  Session,
  SnapshotPoint,
  TradeReceipt,
  TradeRecord,
} from "../types";

function toPosition(raw: RawPosition): Position {
  return {
    ticker: raw.ticker,
    quantity: raw.quantity,
    avgCost: raw.avg_cost,
    currentPrice: raw.current_price,
    marketValue: raw.market_value,
    unrealizedPnl: raw.unrealized_pnl,
    pctChange: raw.pct_change,
  };
}

function toAction(raw: Record<string, unknown>): ExecutedAction {
  return {
    kind: raw.kind as "trade" | "watchlist",
    ticker: raw.ticker as string,
    status: raw.status as "ok" | "error",
    detail: (raw.detail ?? {}) as Record<string, unknown>,
    errorCode: (raw.error_code ?? null) as string | null,
    errorMessage: (raw.error_message ?? null) as string | null,
  };
}

export async function fetchPortfolio(): Promise<Portfolio> {
  const raw = await api.get<{
    cash_balance: number;
    positions: RawPosition[];
    positions_value: number;
    total_value: number;
    unrealized_pnl: number;
  }>("/api/portfolio");

  return {
    cashBalance: raw.cash_balance,
    positions: raw.positions.map(toPosition),
    positionsValue: raw.positions_value,
    totalValue: raw.total_value,
    unrealizedPnl: raw.unrealized_pnl,
  };
}

export async function executeTrade(
  ticker: string,
  side: "buy" | "sell",
  quantity: number,
): Promise<TradeReceipt> {
  const raw = await api.post<RawTradeReceipt>("/api/portfolio/trade", {
    ticker,
    side,
    quantity,
  });
  return {
    id: raw.trade.id,
    ticker: raw.trade.ticker,
    side: raw.trade.side,
    quantity: raw.trade.quantity,
    price: raw.trade.price,
    executedAt: raw.trade.executed_at,
    cashBalance: raw.cash_balance,
    position: raw.position && {
      quantity: raw.position.quantity,
      avgCost: raw.position.avg_cost,
    },
    realizedPnl: raw.realized_pnl,
    totalValue: raw.total_value,
  };
}

export async function fetchPortfolioHistory(limit = 500): Promise<SnapshotPoint[]> {
  const raw = await api.get<{ snapshots: { total_value: number; recorded_at: string }[] }>(
    `/api/portfolio/history?limit=${limit}`,
  );
  return raw.snapshots.map((s) => ({ totalValue: s.total_value, recordedAt: s.recorded_at }));
}

export async function fetchTrades(limit = 200): Promise<TradeRecord[]> {
  const raw = await api.get<{
    trades: {
      id: string;
      ticker: string;
      side: "buy" | "sell";
      quantity: number;
      price: number;
      executed_at: string;
      value: number;
      realized_pnl: number | null;
    }[];
  }>(`/api/portfolio/trades?limit=${limit}`);
  return raw.trades.map((t) => ({
    id: t.id,
    ticker: t.ticker,
    side: t.side,
    quantity: t.quantity,
    price: t.price,
    executedAt: t.executed_at,
    value: t.value,
    realizedPnl: t.realized_pnl,
  }));
}

export async function fetchWatchlist(): Promise<{ tickers: string[]; cap: number }> {
  return api.get("/api/watchlist");
}

export async function addToWatchlist(ticker: string): Promise<string[]> {
  const raw = await api.post<{ tickers: string[] }>("/api/watchlist", { ticker });
  return raw.tickers;
}

export async function removeFromWatchlist(ticker: string): Promise<string[]> {
  const raw = await api.delete<{ tickers: string[] }>(`/api/watchlist/${ticker}`);
  return raw.tickers;
}

export async function fetchHistory(ticker: string): Promise<HistoryPoint[]> {
  const raw = await api.get<{ points: HistoryPoint[] }>(`/api/history/${ticker}`);
  return raw.points;
}

export async function fetchChatHistory(): Promise<ChatMessage[]> {
  const raw = await api.get<{ messages: Record<string, unknown>[] }>("/api/chat");
  return raw.messages.map((m) => ({
    id: m.id as string,
    role: m.role as "user" | "assistant",
    content: m.content as string,
    actions: m.actions ? (m.actions as Record<string, unknown>[]).map(toAction) : null,
    createdAt: m.created_at as string,
  }));
}

export async function sendChatMessage(message: string): Promise<ChatReply> {
  const raw = await api.post<{
    message: string;
    actions: Record<string, unknown>[];
    error: boolean;
  }>("/api/chat", { message }, { timeoutMs: CHAT_TIMEOUT_MS });
  return { message: raw.message, actions: raw.actions.map(toAction), error: raw.error };
}

export async function resetAll(): Promise<void> {
  await api.post("/api/reset");
}

export async function fetchSession(): Promise<Session> {
  return api.get<Session>("/api/auth/me");
}

export async function fetchProviders(): Promise<AuthProvider[]> {
  const body = await api.get<{ providers: AuthProvider[] }>("/api/auth/providers");
  return body.providers;
}

export async function logout(): Promise<void> {
  await api.post<{ ok: boolean }>("/api/auth/logout");
}

export async function confirmClaim(token: string): Promise<void> {
  await api.post<unknown>("/api/auth/claim", { token });
}
