"use client";

import { memo } from "react";
import { instrumentColor } from "@/lib/theme";
import { instrumentMonogram } from "@/lib/instruments";

const SIZES = {
  sm: "h-6 w-6 text-[9px]",
  md: "h-9 w-9 text-[11px]",
} as const;

/**
 * An instrument's identity mark.
 *
 * The colour is derived from the symbol itself, so the same holding wears the
 * same colour in the watchlist, the positions table, the allocation bar, and
 * the assistant's trade receipts. It is decorative for a sighted user reading
 * the symbol beside it, so it is hidden from assistive technology.
 *
 * Memoized because it sits inside panels that re-render on every price tick,
 * while its own props change only when the holding does.
 */
export const TickerChip = memo(function TickerChip({
  ticker,
  size = "md",
}: {
  ticker: string;
  size?: keyof typeof SIZES;
}) {
  return (
    <span
      aria-hidden="true"
      style={{ backgroundColor: instrumentColor(ticker) }}
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-display font-bold uppercase tracking-tight text-white ${SIZES[size]}`}
    >
      {instrumentMonogram(ticker)}
    </span>
  );
});
