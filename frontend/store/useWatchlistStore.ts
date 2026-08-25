"use client";

/** Watchlist membership, ordering, and the selected ticker. */

import { create } from "zustand";
import { addToWatchlist, fetchWatchlist, removeFromWatchlist } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { LoadState } from "@/lib/types";

interface WatchlistState {
  tickers: string[];
  cap: number;
  /** How the first fetch went, so the panel can tell "no tickers" apart
   *  from "not asked yet" and from "asked, and it failed". */
  status: LoadState;
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
  status: "pending" as LoadState,
  selectedTicker: null,
  error: null,

  refresh: async () => {
    try {
      const { tickers, cap } = await fetchWatchlist();
      // Order comes from the server (added_at), never from the SSE frame, so
      // rows stay put as prices update.
      set({
        tickers,
        cap,
        status: "ready",
        selectedTicker: get().selectedTicker ?? tickers[0] ?? null,
      });
    } catch (error) {
      // Nothing else retries this and `useAppBoot` settles the rejection, so
      // a status left at "pending" here is a skeleton that never resolves.
      set({ status: "failed" });
      throw error;
    }
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
