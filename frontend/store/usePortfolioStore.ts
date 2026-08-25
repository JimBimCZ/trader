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
    try {
      await executeTrade(ticker, side, quantity);
      await get().refresh();
      await get().refreshHistory();
      return true;
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "The trade could not be completed.";
      set({ tradeError: message });
      return false;
    } finally {
      set({ tradePending: false });
    }
  },

  clearTradeError: () => set({ tradeError: null }),
}));
