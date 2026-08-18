"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { PriceCell } from "../ui/PriceCell";
import { ChangeBadge } from "../ui/ChangeBadge";
import { Sparkline } from "../ui/Sparkline";

export function WatchlistRow({ ticker }: { ticker: string }) {
  const selected = useWatchlistStore((s) => s.selectedTicker === ticker);
  const select = useWatchlistStore((s) => s.select);
  const remove = useWatchlistStore((s) => s.remove);
  const dailyChange = usePriceStore((s) => s.prices[ticker]?.dailyChangePercent ?? 0);

  return (
    <div
      className={`group grid grid-cols-[1fr_auto_auto] items-center gap-2 border-b border-border/60 px-3 py-1.5 text-xs ${
        selected ? "bg-yellow/10 border-l-2 border-l-yellow" : "border-l-2 border-l-transparent"
      }`}
      data-testid={`watchlist-row-${ticker}`}
    >
      <button
        onClick={() => select(ticker)}
        className="flex items-center gap-2 text-left font-semibold tracking-wider text-text"
        aria-pressed={selected}
        data-testid={`select-${ticker}`}
      >
        {ticker}
      </button>

      <Sparkline ticker={ticker} />

      <div className="flex items-center gap-2">
        <div className="flex w-28 flex-col items-end">
          <PriceCell ticker={ticker} />
          <ChangeBadge value={dailyChange} testId={`change-${ticker}`} />
        </div>
        <button
          onClick={() => remove(ticker)}
          aria-label={`Remove ${ticker} from watchlist`}
          data-testid={`remove-${ticker}`}
          className="opacity-0 transition group-hover:opacity-100 focus:opacity-100 text-flat hover:text-down-text"
        >
          ×
        </button>
      </div>
    </div>
  );
}
