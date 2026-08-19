"use client";

import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { valuePortfolio } from "@/lib/portfolio";
import { instrumentColor } from "@/lib/theme";
import { usePalette } from "@/lib/useTheme";
import { formatPrice, formatSignedPercent } from "@/lib/format";
import { SignedValue } from "../ui/SignedValue";
import { ThemeToggle } from "../ui/ThemeToggle";
import { ConnectionStatusDot } from "./ConnectionStatusDot";

/**
 * The unified toolbar. Chrome rather than a card, so it takes the same
 * translucent material as the sidebar.
 */
export function Header() {
  const cash = usePortfolioStore((s) => s.cashBalance);
  const positions = usePortfolioStore((s) => s.positions);
  const prices = usePriceStore((s) => s.prices);
  const { appearance } = usePalette();

  // Recomputed on every tick from positions x live prices: the REST total is
  // only a reconciliation point, not the live number.
  const { holdings, unrealized, unrealizedPercent, totalValue } = valuePortfolio(
    positions,
    prices,
    cash,
  );

  // Weighed against the whole account, cash included, so the gap at the end
  // of the bar is the uninvested balance.
  const share = (value: number) => (totalValue ? (value / totalValue) * 100 : 0);

  return (
    <header className="rise material flex flex-wrap items-center justify-between gap-x-8 gap-y-4 px-5 py-3.5">
      <div className="min-w-0">
        <p className="field-label">Portfolio value</p>
        <div className="mt-1 flex flex-wrap items-baseline gap-2.5">
          <span
            className="text-[34px] font-bold leading-none tracking-[-0.03em] text-text"
            data-testid="total-value"
          >
            {formatPrice(totalValue)}
          </span>
          <span className="text-[13px] font-semibold" data-testid="unrealized-pnl">
            <SignedValue value={unrealized} />
            <span className="ml-1 opacity-70">({formatSignedPercent(unrealizedPercent)})</span>
          </span>
        </div>
      </div>

      {/* Each segment wears the holding's own colour, the same one it carries
          in the watchlist and the positions table. */}
      <div className="min-w-[200px] flex-1">
        <div className="flex items-baseline justify-between">
          <p className="field-label">Allocation</p>
          <p className="text-[12px] font-medium text-text-muted">
            <span className="text-text" data-testid="cash-balance">
              {formatPrice(cash)}
            </span>{" "}
            cash
          </p>
        </div>
        <div
          className="mt-2 flex h-2 gap-[2px] overflow-hidden rounded-full bg-surface-sunk"
          role="img"
          aria-label={
            holdings.length
              ? `Allocation: ${holdings
                  .map((h) => `${h.ticker} ${share(h.value).toFixed(0)}%`)
                  .join(", ")}, cash ${share(cash).toFixed(0)}%`
              : "Allocation: all cash"
          }
        >
          {holdings.map((holding) => (
            <span
              key={holding.ticker}
              title={`${holding.ticker} · ${formatPrice(holding.value)}`}
              className="rounded-full"
              style={{
                width: `${share(holding.value)}%`,
                backgroundColor: instrumentColor(holding.ticker, appearance),
              }}
            />
          ))}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2.5">
        <ConnectionStatusDot />
        <ThemeToggle />
      </div>
    </header>
  );
}
