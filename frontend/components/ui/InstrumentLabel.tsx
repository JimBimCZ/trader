"use client";

import { instrumentName } from "@/lib/instruments";
import { TickerChip } from "./TickerChip";

/**
 * An instrument, named.
 *
 * The chip plus the symbol plus the company beneath it is the app's most
 * repeated visual unit — it heads the chart, labels every watchlist row, and
 * opens every positions row. One component so the identity treatment is one
 * decision rather than three that drift.
 */
export function InstrumentLabel({
  ticker,
  size = "sm",
}: {
  ticker: string;
  size?: "sm" | "md";
}) {
  const name = instrumentName(ticker);

  return (
    <span className="flex min-w-0 items-center gap-2.5">
      <TickerChip ticker={ticker} size={size} />
      <span className="min-w-0">
        <span className="block truncate font-display text-[13px] font-bold tracking-tight text-text">
          {ticker}
        </span>
        {name && (
          <span className="block truncate font-sans text-[11px] font-normal text-text-muted">
            {name}
          </span>
        )}
      </span>
    </span>
  );
}
