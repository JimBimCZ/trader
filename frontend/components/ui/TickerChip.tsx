"use client";

import { memo } from "react";
import { instrumentColor } from "@/lib/theme";
import { usePalette } from "@/lib/useTheme";
import { instrumentMonogram } from "@/lib/instruments";

const SIZES = {
  sm: "h-6 w-6 text-[9px]",
  md: "h-8 w-8 text-[11px]",
} as const;

/**
 * An instrument's identity mark.
 *
 * The colour is derived from the symbol itself, so the same holding wears the
 * same colour in the watchlist, the positions table, the allocation bar, and
 * the assistant's trade receipts. It is the one colour in the app that cannot
 * be a custom property — there is a hue per symbol, not per token — so it is
 * the reason components read the palette from the store at all.
 *
 * It is decorative for a sighted user reading the symbol beside it, so it is
 * hidden from assistive technology.
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
  const { appearance, colors } = usePalette();

  return (
    <span
      aria-hidden="true"
      style={{
        backgroundColor: instrumentColor(ticker, appearance),
        // The dark hues are bright enough that near-black is the legible
        // monogram, so the ink follows the appearance rather than being white
        // in both and unreadable in one.
        color: colors.instrumentInk,
      }}
      className={`chip inline-flex shrink-0 items-center justify-center rounded-full font-semibold uppercase tracking-tight ${SIZES[size]}`}
    >
      {instrumentMonogram(ticker)}
    </span>
  );
});
