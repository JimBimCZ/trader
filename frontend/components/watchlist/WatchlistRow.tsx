"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { PriceCell } from "../ui/PriceCell";
import { ChangeBadge } from "../ui/ChangeBadge";
import { Sparkline } from "../ui/Sparkline";
import { InstrumentLabel } from "../ui/InstrumentLabel";
import { CloseIcon } from "../ui/icons";

export function WatchlistRow({ ticker }: { ticker: string }) {
  const selected = useWatchlistStore((s) => s.selectedTicker === ticker);
  const select = useWatchlistStore((s) => s.select);
  const remove = useWatchlistStore((s) => s.remove);
  const dailyChange = usePriceStore((s) => s.prices[ticker]?.dailyChangePercent ?? 0);

  return (
    <div
      className={`group relative flex items-center gap-3 rounded-xl px-2.5 py-2 transition ${
        selected ? "bg-surface-sunk" : "hover:bg-surface-alt"
      }`}
      data-testid={`watchlist-row-${ticker}`}
    >
      {selected && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1/2 h-7 w-1 -translate-y-1/2 rounded-r-full bg-brand"
        />
      )}

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

      <div className="flex w-[84px] shrink-0 flex-col items-end gap-0.5">
        <PriceCell ticker={ticker} className="text-[13px]" />
        <ChangeBadge value={dailyChange} testId={`change-${ticker}`} />
      </div>

      {/* Absolute, so the column it would occupy is not held open for a
          control that only exists on hover. */}
      <button
        onClick={() => remove(ticker)}
        aria-label={`Remove ${ticker} from watchlist`}
        data-testid={`remove-${ticker}`}
        className="absolute -right-0.5 top-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-surface text-text-faint opacity-0 shadow-card transition hover:bg-down-wash hover:text-down-text group-hover:opacity-100 focus:opacity-100"
      >
        <CloseIcon />
      </button>
    </div>
  );
}
