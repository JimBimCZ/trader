"use client";

import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { formatPrice, formatQuantity, formatSignedCurrency } from "@/lib/format";
import { ChangeBadge } from "../ui/ChangeBadge";

export function PositionsTable() {
  const positions = usePortfolioStore((s) => s.positions);
  const watched = useWatchlistStore((s) => s.tickers);
  const select = useWatchlistStore((s) => s.select);
  const livePrices = usePriceStore((s) => s.prices);

  return (
    <section className="panel flex min-h-0 flex-col" aria-label="Positions">
      <header className="panel-title">Positions</header>

      {positions.length === 0 ? (
        <p className="px-3 py-6 text-center text-xs text-text-muted">
          No open positions. Buy something to get started.
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-xs" data-testid="positions-table">
            <thead className="sticky top-0 bg-bg-alt text-[10px] uppercase tracking-wider text-text-muted">
              <tr className="border-b border-border">
                <th className="px-3 py-1.5 text-left font-medium">Ticker</th>
                <th className="px-3 py-1.5 text-right font-medium">Qty</th>
                <th className="px-3 py-1.5 text-right font-medium">Avg cost</th>
                <th className="px-3 py-1.5 text-right font-medium">Price</th>
                <th className="px-3 py-1.5 text-right font-medium">P&amp;L</th>
                <th className="px-3 py-1.5 text-right font-medium">Return</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                // Prefer the live price so the table moves with the stream
                // between portfolio refreshes.
                const price = livePrices[position.ticker]?.price ?? position.currentPrice;
                const pnl = (price - position.avgCost) * position.quantity;
                const pct = position.avgCost
                  ? ((price - position.avgCost) / position.avgCost) * 100
                  : 0;
                const unwatched = !watched.includes(position.ticker);

                return (
                  <tr
                    key={position.ticker}
                    onClick={() => select(position.ticker)}
                    className="cursor-pointer border-b border-border/50 hover:bg-bg-raised"
                    data-testid={`position-${position.ticker}`}
                  >
                    <td className="px-3 py-1.5 font-semibold tracking-wider">
                      {position.ticker}
                      {unwatched && (
                        <span
                          title="Held but not on your watchlist"
                          className="ml-1.5 rounded border border-border px-1 text-[9px] uppercase text-flat"
                        >
                          unwatched
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {formatQuantity(position.quantity)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-text-muted">
                      {formatPrice(position.avgCost)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{formatPrice(price)}</td>
                    <td
                      className={`px-3 py-1.5 text-right tabular-nums ${
                        pnl > 0 ? "text-up-text" : pnl < 0 ? "text-down-text" : "text-flat"
                      }`}
                    >
                      {formatSignedCurrency(pnl)}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <ChangeBadge value={pct} />
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
