"use client";

/** Portfolio state, refreshed from REST after every mutation. */

import { create } from "zustand";
import { executeTrade, fetchPortfolio, fetchPortfolioHistory } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { Portfolio, Position, SnapshotPoint } from "@/lib/types";

interface PortfolioState {
  cashBalance: number;
  positions: Position[];
  totalValue: number;
  unrealizedPnl: number;
  history: SnapshotPoint[];
  loaded: boolean;
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
    loaded: true,
  };
}

export const usePortfolioStore = create<PortfolioState>()((set, get) => ({
  cashBalance: 0,
  positions: [],
  totalValue: 0,
  unrealizedPnl: 0,
  history: [],
  loaded: false,
  tradeError: null,
  tradePending: false,

  refresh: async () => {
    set(applyPortfolio(await fetchPortfolio()));
  },

  refreshHistory: async () => {
    set({ history: await fetchPortfolioHistory() });
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
