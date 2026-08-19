/**
 * Live price state, kept in its own store so a 2Hz tick cannot notify
 * subscribers of the portfolio, watchlist, or chat stores.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type { ConnectionStatus, PriceFrame, PriceSnapshot, RawPriceUpdate } from "../types";

/** Points kept per sparkline. Enough for shape, small enough to stay cheap. */
export const SPARKLINE_POINTS = 60;

export function normalize(raw: RawPriceUpdate): PriceSnapshot {
  return {
    ticker: raw.ticker,
    price: raw.price,
    previousPrice: raw.previous_price,
    sessionOpen: raw.session_open,
    timestamp: raw.timestamp,
    // The daily field, never change_percent, which is tick-over-tick and
    // sits near zero.
    dailyChangePercent: raw.daily_change_percent,
    direction: raw.direction,
  };
}

interface PriceState {
  prices: Record<string, PriceSnapshot>;
  sparklines: Record<string, number[]>;
  connectionStatus: ConnectionStatus;
  applyFrame: (frame: PriceFrame) => void;
  seedSparkline: (ticker: string, points: number[]) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  reset: () => void;
}

export const usePriceStore = create<PriceState>()(
  subscribeWithSelector((set) => ({
    prices: {},
    sparklines: {},
    connectionStatus: "connecting",

    applyFrame: (frame) =>
      set((state) => {
        const prices = { ...state.prices };
        const sparklines = { ...state.sparklines };

        for (const [ticker, raw] of Object.entries(frame)) {
          prices[ticker] = normalize(raw);
          // Trim before appending, so a full buffer is copied once per frame
          // rather than grown and then re-sliced.
          const existing = sparklines[ticker];
          const next = existing
            ? existing.slice(Math.max(0, existing.length - SPARKLINE_POINTS + 1))
            : [];
          next.push(raw.price);
          sparklines[ticker] = next;
        }

        return { prices, sparklines };
      }),

    seedSparkline: (ticker, points) =>
      set((state) => ({
        sparklines: { ...state.sparklines, [ticker]: points.slice(-SPARKLINE_POINTS) },
      })),

    setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

    reset: () => set({ prices: {}, sparklines: {} }),
  })),
);
