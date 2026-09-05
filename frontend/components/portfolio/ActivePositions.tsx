"use client";

import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { valueHolding } from "@/lib/portfolio";
import { formatPrice, formatQuantity } from "@/lib/format";
import { ChangeBadge } from "../ui/ChangeBadge";
import { TickerChip } from "../ui/TickerChip";
import { SkeletonRow } from "../ui/Skeleton";
import { LoadFailure } from "../ui/LoadFailure";

/**
 * The overview's glance at what is open, sharing the right column with the
 * assistant.
 *
 * Not `PositionsTable` with columns hidden: that table is six columns wide
 * and this column is 320px, so the two want different rows rather than the
 * same rows at two densities. This one drops avg cost and P&L in dollars —
 * both a click away on `/portfolio/` — and keeps what a glance is for: what
 * is held, what it is worth now, and which way it has gone.
 */
export function ActivePositions() {
  const positions = usePortfolioStore((s) => s.positions);
  const status = usePortfolioStore((s) => s.status);
  const refresh = usePortfolioStore((s) => s.refresh);
  const selectedTicker = useWatchlistStore((s) => s.selectedTicker);
  const select = useWatchlistStore((s) => s.select);
  const livePrices = usePriceStore((s) => s.prices);

  return (
    <section
      id="panel-active-positions"
      className="rise card flex flex-col overflow-hidden lg:min-h-0"
      aria-label="Active positions"
    >
      <header className="card-title">
        <span>Positions</span>
        <span className="text-[11px] font-medium text-text-muted">
          {status === "ready" ? `${positions.length} open` : "—"}
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="active-positions">
        {status === "pending" ? (
          Array.from({ length: 3 }, (_, i) => <SkeletonRow key={`skeleton-${i}`} />)
        ) : status === "failed" ? (
          <LoadFailure what="your positions" onRetry={refresh} />
        ) : positions.length === 0 ? (
          <p className="px-4 py-8 text-center text-[13px] text-text-muted">
            Nothing open yet. Buy a symbol and it appears here.
          </p>
        ) : (
          positions.map((position) => {
            const { price, value, pctChange } = valueHolding(position, livePrices);
            const selected = selectedTicker === position.ticker;

            return (
              <button
                key={position.ticker}
                onClick={() => select(position.ticker)}
                aria-pressed={selected}
                data-selected={selected}
                // The separator starts where the symbol does, past the chip.
                style={{ "--row-inset": "3.25rem" } as React.CSSProperties}
                className={`list-row flex w-full items-center gap-3 px-3 py-2 text-left transition ${
                  selected ? "bg-blue/10" : "hover:bg-surface-alt"
                }`}
                data-testid={`active-position-${position.ticker}`}
              >
                <TickerChip ticker={position.ticker} size="md" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold tracking-[-0.01em] text-text">
                    {position.ticker}
                  </span>
                  <span className="block truncate text-[11px] text-text-muted">
                    {formatQuantity(position.quantity)} @ {formatPrice(price)}
                  </span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-0.5">
                  <span className="text-[13px] font-semibold">{formatPrice(value)}</span>
                  <ChangeBadge value={pctChange} testId={`active-return-${position.ticker}`} />
                </span>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
