"use client";

import { useEffect } from "react";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { formatIsoClock, formatPrice, formatQuantity } from "@/lib/format";
import { InstrumentLabel } from "../ui/InstrumentLabel";
import { SignedValue } from "../ui/SignedValue";
import { SkeletonRow } from "../ui/Skeleton";
import { LoadFailure } from "../ui/LoadFailure";

/**
 * Every fill, newest first, and what each sale made.
 *
 * The action column is past tense on both sides -- "Bought", "Sold" -- which
 * is how the trade receipt and the assistant's inline receipts already speak
 * about an order that has filled.
 */
export function TradeHistoryTable() {
  const trades = usePortfolioStore((s) => s.trades);
  const status = usePortfolioStore((s) => s.tradesStatus);
  const refreshTrades = usePortfolioStore((s) => s.refreshTrades);

  useEffect(() => {
    // Swallowed, not ignored: refreshTrades records the outcome on the store,
    // which is what the branch below renders.
    void refreshTrades().catch(() => {});
  }, [refreshTrades]);

  return (
    <section
      id="panel-history"
      className="rise card flex flex-1 flex-col overflow-hidden lg:min-h-0"
      aria-label="Trade history"
    >
      <header className="card-title">
        <span>History</span>
        <span className="text-[11px] font-medium text-text-muted">
          {status === "ready" ? `${trades.length} fills` : "—"}
        </span>
      </header>

      {status === "pending" ? (
        <div className="py-1">
          {Array.from({ length: 4 }, (_, i) => (
            <SkeletonRow key={`skeleton-${i}`} />
          ))}
        </div>
      ) : status === "failed" ? (
        <LoadFailure what="your trade history" onRetry={refreshTrades} />
      ) : trades.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-text-muted">
          No trades yet. Every order you place shows up here.
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-[13px]" data-testid="trade-history">
            <thead className="sticky top-0 bg-surface text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
              <tr>
                <th className="px-3 pb-2 pt-1 text-left">Time</th>
                <th className="px-3 pb-2 pt-1 text-left">Instrument</th>
                <th className="px-3 pb-2 pt-1 text-left">Action</th>
                <th className="px-3 pb-2 pt-1 text-right">Units</th>
                <th className="px-3 pb-2 pt-1 text-right">Price</th>
                <th className="px-3 pb-2 pt-1 text-right">Value</th>
                <th className="px-3 pb-2 pt-1 text-right">Realized</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr
                  key={trade.id}
                  className="border-t-hairline border-border"
                  data-testid={`trade-${trade.id}`}
                >
                  <td className="px-3 py-2 text-text-muted">
                    {formatIsoClock(trade.executedAt)}
                  </td>
                  <td className="px-3 py-2">
                    <InstrumentLabel ticker={trade.ticker} />
                  </td>
                  <td className="px-3 py-2 font-medium">
                    {trade.side === "buy" ? "Bought" : "Sold"}
                  </td>
                  <td className="px-3 py-2 text-right">{formatQuantity(trade.quantity)}</td>
                  <td className="px-3 py-2 text-right text-text-muted">
                    {formatPrice(trade.price)}
                  </td>
                  <td className="px-3 py-2 text-right font-semibold">
                    {formatPrice(trade.value)}
                  </td>
                  <td className="px-3 py-2 text-right font-semibold">
                    {/* A buy realizes nothing. An em dash says that; a 0.00
                        would read as "broke even", which is a different claim. */}
                    {trade.realizedPnl === null ? (
                      <span aria-label="not applicable">&mdash;</span>
                    ) : (
                      <SignedValue value={trade.realizedPnl} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
