"use client";

import { instrumentName } from "@/lib/instruments";
import { TickerChip } from "./TickerChip";

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
        <span className="block truncate text-[13px] font-semibold tracking-[-0.01em] text-text">
          {ticker}
        </span>
        {name && (
          <span className="block truncate text-[11px] font-normal text-text-muted">{name}</span>
        )}
      </span>
    </span>
  );
}
