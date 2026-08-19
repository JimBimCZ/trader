"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import { formatPrice } from "@/lib/format";

/**
 * A live price with a flash on change. The flash class is derived during the
 * render the price change already causes, and the key forces the CSS animation
 * to restart — no timer, no extra state.
 */
export function PriceCell({
  ticker,
  className = "",
  testId,
}: {
  ticker: string;
  className?: string;
  /** Defaults to the watchlist's id; a second instance must pass its own. */
  testId?: string;
}) {
  const snapshot = usePriceStore((state) => state.prices[ticker]);

  if (!snapshot) {
    return <span className={`text-text-faint ${className}`}>—</span>;
  }

  const flash =
    snapshot.direction === "up" ? "flash-up" : snapshot.direction === "down" ? "flash-down" : "";

  return (
    <span
      key={snapshot.timestamp}
      className={`rounded-[6px] px-1 font-semibold text-text ${flash} ${className}`}
      data-testid={testId ?? `price-${ticker}`}
    >
      {formatPrice(snapshot.price)}
    </span>
  );
}
