"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import { formatPrice } from "@/lib/format";

/**
 * A live price with a flash on change.
 *
 * The flash class is derived during the render the price change already
 * causes, and the key forces the CSS animation to restart. No timer, no extra
 * state, no second render to clear the highlight.
 */
export function PriceCell({ ticker }: { ticker: string }) {
  const snapshot = usePriceStore((state) => state.prices[ticker]);

  if (!snapshot) {
    return <span className="tabular-nums text-flat">—</span>;
  }

  const flash =
    snapshot.direction === "up" ? "flash-up" : snapshot.direction === "down" ? "flash-down" : "";

  return (
    <span
      key={snapshot.timestamp}
      className={`rounded px-1 tabular-nums text-text ${flash}`}
      data-testid={`price-${ticker}`}
    >
      {formatPrice(snapshot.price)}
    </span>
  );
}
