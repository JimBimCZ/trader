"use client";

import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { formatPrice, formatSignedCurrency, toneClass, directionGlyph } from "@/lib/format";
import { ConnectionStatusDot } from "./ConnectionStatusDot";

export function Header() {
  const cash = usePortfolioStore((s) => s.cashBalance);
  const positions = usePortfolioStore((s) => s.positions);
  const prices = usePriceStore((s) => s.prices);

  // Recomputed on every tick from positions x live prices: the REST total is
  // only a reconciliation point, not the live number.
  let positionsValue = 0;
  let costBasis = 0;
  for (const position of positions) {
    const price = prices[position.ticker]?.price ?? position.currentPrice;
    positionsValue += position.quantity * price;
    costBasis += position.quantity * position.avgCost;
  }
  const totalValue = cash + positionsValue;
  const unrealized = positionsValue - costBasis;

  return (
    <header className="panel flex flex-wrap items-center justify-between gap-4 px-4 py-2">
      <div className="flex items-baseline gap-3">
        <span className="text-sm font-bold uppercase tracking-[0.3em] text-yellow">Trader</span>
        <span className="text-[10px] uppercase tracking-wider text-flat">AI workstation</span>
      </div>

      <dl className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs">
        <div className="flex items-baseline gap-2">
          <dt className="uppercase tracking-wider text-text-muted">Total</dt>
          <dd className="tabular-nums text-base font-semibold text-text" data-testid="total-value">
            {formatPrice(totalValue)}
          </dd>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="uppercase tracking-wider text-text-muted">Unrealized</dt>
          <dd className={`tabular-nums ${toneClass(unrealized)}`} data-testid="unrealized-pnl">
            <span aria-hidden="true">{directionGlyph(unrealized)} </span>
            {formatSignedCurrency(unrealized)}
          </dd>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="uppercase tracking-wider text-text-muted">Cash</dt>
          <dd className="tabular-nums text-text" data-testid="cash-balance">
            {formatPrice(cash)}
          </dd>
        </div>
      </dl>

      <ConnectionStatusDot />
    </header>
  );
}
