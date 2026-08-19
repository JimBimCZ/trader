"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { PriceCell } from "../ui/PriceCell";
import { ChangeBadge } from "../ui/ChangeBadge";
import { Sparkline } from "../ui/Sparkline";
import { InstrumentLabel } from "../ui/InstrumentLabel";
import { CloseIcon } from "../ui/icons";

/**
 * One row of the grouped inset list. The `data-selected` attribute is what
 * tells the separator above it to step aside.
 */
export function WatchlistRow({ ticker }: { ticker: string }) {
  const selected = useWatchlistStore((s) => s.selectedTicker === ticker);
  const select = useWatchlistStore((s) => s.select);
  const remove = useWatchlistStore((s) => s.remove);
  const dailyChange = usePriceStore((s) => s.prices[ticker]?.dailyChangePercent ?? 0);

  return (
    <div
      data-selected={selected}
      // The separator starts where the symbol does, past the chip.
      style={{ "--row-inset": "3.25rem" } as React.CSSProperties}
      className={`list-row group flex items-center gap-3 px-3 py-2 transition ${
        selected ? "bg-blue/10" : "hover:bg-surface-alt"
      }`}
      data-testid={`watchlist-row-${ticker}`}
    >
      <button
        onClick={() => select(ticker)}
        className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
        aria-pressed={selected}
        data-testid={`select-${ticker}`}
      >
        <InstrumentLabel ticker={ticker} size="md" />
      </button>

      <span className="shrink-0">
        <Sparkline ticker={ticker} />
      </span>

      <div className="flex w-[80px] shrink-0 flex-col items-end gap-0.5">
        <PriceCell ticker={ticker} className="text-[13px]" />
        <ChangeBadge value={dailyChange} testId={`change-${ticker}`} />
      </div>

      {/* Absolute, so the column it would occupy is not held open for a
          control that only exists on hover. */}
      <button
        onClick={() => remove(ticker)}
        aria-label={`Remove ${ticker} from watchlist`}
        data-testid={`remove-${ticker}`}
        className="absolute right-1.5 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-surface text-text-faint opacity-0 shadow-card transition hover:bg-down hover:text-white group-hover:opacity-100 focus:opacity-100"
      >
        <CloseIcon className="h-3 w-3" />
      </button>
    </div>
  );
}
