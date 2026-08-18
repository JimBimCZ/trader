"use client";

/** Watchlist membership, ordering, and the selected ticker. */

import { create } from "zustand";
import { addToWatchlist, fetchWatchlist, removeFromWatchlist } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";

interface WatchlistState {
  tickers: string[];
  cap: number;
  selectedTicker: string | null;
  error: string | null;
  refresh: () => Promise<void>;
  add: (ticker: string) => Promise<boolean>;
  remove: (ticker: string) => Promise<void>;
  select: (ticker: string) => void;
  clearError: () => void;
}

export const useWatchlistStore = create<WatchlistState>()((set, get) => ({
  tickers: [],
  cap: 25,
  selectedTicker: null,
  error: null,

  refresh: async () => {
    const { tickers, cap } = await fetchWatchlist();
    // Order comes from the server (added_at), never from the SSE frame, so
    // rows stay put as prices update.
    set({ tickers, cap, selectedTicker: get().selectedTicker ?? tickers[0] ?? null });
  },

  add: async (ticker) => {
    try {
      set({ tickers: await addToWatchlist(ticker), error: null });
      return true;
    } catch (error) {
      set({ error: error instanceof ApiError ? error.message : "Could not add that ticker." });
      return false;
    }
  },

  remove: async (ticker) => {
    const tickers = await removeFromWatchlist(ticker);
    const { selectedTicker } = get();
    set({
      tickers,
      selectedTicker: selectedTicker === ticker ? (tickers[0] ?? null) : selectedTicker,
    });
  },

  select: (selectedTicker) => set({ selectedTicker }),
  clearError: () => set({ error: null }),
}));
