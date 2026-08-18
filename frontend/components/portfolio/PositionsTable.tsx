"use client";

import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { valueHolding } from "@/lib/portfolio";
import { formatPrice, formatQuantity } from "@/lib/format";
import { ChangeBadge } from "../ui/ChangeBadge";
import { InstrumentLabel } from "../ui/InstrumentLabel";
import { SignedValue } from "../ui/SignedValue";
import { PANELS } from "../layout/panels";

export function PositionsTable() {
  const positions = usePortfolioStore((s) => s.positions);
  const watched = useWatchlistStore((s) => s.tickers);
  const select = useWatchlistStore((s) => s.select);
  const livePrices = usePriceStore((s) => s.prices);

  return (
    <section
      id={PANELS.portfolio.id}
      className="rise card flex flex-col lg:min-h-0"
      aria-label="Positions"
    >
      <header className="card-title">
        <span>Positions</span>
        <span className="text-[11px] font-medium text-text-muted">
          {positions.length} open
        </span>
      </header>

      {positions.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-text-muted">
          No open positions. Buy a symbol to start building the portfolio.
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
          <table className="w-full text-[13px]" data-testid="positions-table">
            <thead className="sticky top-0 bg-surface font-display text-[11px] font-bold uppercase tracking-[0.1em] text-text-muted">
              <tr>
                <th className="px-3 pb-2 pt-1 text-left">Instrument</th>
                <th className="px-3 pb-2 pt-1 text-right">Units</th>
                <th className="px-3 pb-2 pt-1 text-right">Avg cost</th>
                <th className="px-3 pb-2 pt-1 text-right">Price</th>
                <th className="px-3 pb-2 pt-1 text-right">P&amp;L</th>
                <th className="px-3 pb-2 pt-1 text-right">Return</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                const { price, pnl, pctChange } = valueHolding(position, livePrices);
                const unwatched = !watched.includes(position.ticker);

                return (
                  <tr
                    key={position.ticker}
                    onClick={() => select(position.ticker)}
                    className="cursor-pointer border-t border-border transition hover:bg-surface-alt"
                    data-testid={`position-${position.ticker}`}
                  >
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-2.5">
                        <InstrumentLabel ticker={position.ticker} />
                        {unwatched && (
                          <span
                            title="Held but not on your watchlist"
                            className="rounded-full bg-surface-sunk px-2 py-0.5 text-[10px] font-semibold text-text-muted"
                          >
                            unwatched
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">{formatQuantity(position.quantity)}</td>
                    <td className="px-3 py-2 text-right text-text-muted">
                      {formatPrice(position.avgCost)}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold">{formatPrice(price)}</td>
                    <td className="px-3 py-2 text-right font-semibold">
                      <SignedValue value={pnl} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <ChangeBadge value={pctChange} pill />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
