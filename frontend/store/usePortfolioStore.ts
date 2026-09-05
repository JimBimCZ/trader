"use client";

import { create } from "zustand";
import {
  executeTrade,
  fetchPortfolio,
  fetchPortfolioHistory,
  fetchTrades,
} from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type {
  LoadState,
  Portfolio,
  Position,
  SnapshotPoint,
  TradeReceipt,
  TradeRecord,
} from "@/lib/types";

interface PortfolioState {
  cashBalance: number;
  positions: Position[];
  totalValue: number;
  unrealizedPnl: number;
  history: SnapshotPoint[];
  status: LoadState;
  /** Tracked separately: the history comes from its own endpoint, fetched by
   *  PnlChart on mount rather than by the boot sequence, so `status` says
   *  nothing about whether these points have arrived. */
  historyStatus: LoadState;
  trades: TradeRecord[];
  /** Tracked separately for the same reason `historyStatus` is: the trade log
   *  comes from its own endpoint, fetched by the history page rather than by
   *  the boot sequence, so `status` says nothing about whether it has landed. */
  tradesStatus: LoadState;
  tradeError: string | null;
  tradePending: boolean;
  /** The last fill placed from the trade ticket, until the user dismisses it.
   *  Only the ticket writes it -- the assistant's trades go through
   *  `/api/chat` and report themselves inline in the conversation. */
  lastTrade: TradeReceipt | null;
  refresh: () => Promise<void>;
  refreshHistory: () => Promise<void>;
  refreshTrades: () => Promise<void>;
  trade: (ticker: string, side: "buy" | "sell", quantity: number) => Promise<boolean>;
  clearTradeError: () => void;
  dismissTrade: () => void;
}

function applyPortfolio(portfolio: Portfolio) {
  return {
    cashBalance: portfolio.cashBalance,
    positions: portfolio.positions,
    totalValue: portfolio.totalValue,
    unrealizedPnl: portfolio.unrealizedPnl,
    status: "ready" as LoadState,
  };
}

export const usePortfolioStore = create<PortfolioState>()((set, get) => ({
  cashBalance: 0,
  positions: [],
  totalValue: 0,
  unrealizedPnl: 0,
  history: [],
  status: "pending" as LoadState,
  historyStatus: "pending" as LoadState,
  trades: [],
  tradesStatus: "pending" as LoadState,
  tradeError: null,
  tradePending: false,
  lastTrade: null,

  refresh: async () => {
    try {
      set(applyPortfolio(await fetchPortfolio()));
    } catch (error) {
      set({ status: "failed" });
      throw error;
    }
  },

  refreshHistory: async () => {
    try {
      set({ history: await fetchPortfolioHistory(), historyStatus: "ready" });
    } catch (error) {
      set({ historyStatus: "failed" });
      throw error;
    }
  },

  refreshTrades: async () => {
    try {
      set({ trades: await fetchTrades(), tradesStatus: "ready" });
    } catch (error) {
      set({ tradesStatus: "failed" });
      throw error;
    }
  },

  trade: async (ticker, side, quantity) => {
    set({ tradePending: true, tradeError: null });

    // Placing the order is the only step that can fail the trade.
    let receipt;
    try {
      receipt = await executeTrade(ticker, side, quantity);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "The trade could not be completed.";
      set({ tradeError: message, tradePending: false });
      return false;
    }

    // Shown before the re-reads rather than after them: the receipt describes
    // the fill, which the response above already settled, so it neither waits
    // on those two calls nor becomes wrong when one of them fails.
    set({ lastTrade: receipt });

    // From here the order has filled: the server has already moved the cash
    // and the position. The two calls below only re-read that result, so
    // their failure is a stale screen, not an undone trade -- and reporting
    // it as a rejected order would be a lie about money that has already
    // moved, inviting the user to place the same order twice.
    //
    // `allSettled` so a failed portfolio read still lets the history be
    // fetched, and so neither rejection escapes: each call has already
    // recorded its own outcome on the store, which is what the panels render
    // -- with their own Retry.
    await Promise.allSettled([get().refresh(), get().refreshHistory(), get().refreshTrades()]);
    set({ tradePending: false });
    return true;
  },

  clearTradeError: () => set({ tradeError: null }),

  dismissTrade: () => set({ lastTrade: null }),
}));
