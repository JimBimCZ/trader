"use client";

import { create } from "zustand";
import { executeTrade, fetchPortfolio, fetchPortfolioHistory } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { LoadState, Portfolio, Position, SnapshotPoint } from "@/lib/types";

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
  tradeError: string | null;
  tradePending: boolean;
  refresh: () => Promise<void>;
  refreshHistory: () => Promise<void>;
  trade: (ticker: string, side: "buy" | "sell", quantity: number) => Promise<boolean>;
  clearTradeError: () => void;
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
  tradeError: null,
  tradePending: false,

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

  trade: async (ticker, side, quantity) => {
    set({ tradePending: true, tradeError: null });

    // Placing the order is the only step that can fail the trade.
    try {
      await executeTrade(ticker, side, quantity);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "The trade could not be completed.";
      set({ tradeError: message, tradePending: false });
      return false;
    }

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
    await Promise.allSettled([get().refresh(), get().refreshHistory()]);
    set({ tradePending: false });
    return true;
  },

  clearTradeError: () => set({ tradeError: null }),
}));
