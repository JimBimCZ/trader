"use client";

import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { PANELS, type PanelKey } from "./panels";

/**
 * The navigation rail.
 *
 * On a wide screen every panel it lists is already on the page, so each item
 * earns its place by carrying that panel's live count and by scrolling it
 * into view on the narrow layouts, where the workspace stacks.
 */
const ICONS: Record<PanelKey, string> = {
  watchlist: "M4 6h16M4 12h10M4 18h6",
  chart: "M4 18l5-6 4 3 6.5-8",
  portfolio: "M4 20V9m5 11V4m5 16v-7m5 7V11",
  assistant: "M20 12a8 8 0 1 1-3.2-6.4M20 5v4h-4",
};

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function Rail() {
  const tickers = useWatchlistStore((s) => s.tickers);
  const selected = useWatchlistStore((s) => s.selectedTicker);
  const positions = usePortfolioStore((s) => s.positions);

  // Each entry carries its panel's live count, which is what earns the rail
  // its place on a wide screen where every panel is already visible.
  const badges: Record<PanelKey, string | undefined> = {
    watchlist: String(tickers.length),
    chart: selected ?? undefined,
    portfolio: String(positions.length),
    assistant: undefined,
  };

  return (
    <nav
      aria-label="Sections"
      className="rise flex shrink-0 flex-row items-center gap-1 rounded-card bg-rail px-2 py-2 text-white lg:flex-col lg:items-stretch lg:gap-2 lg:px-2 lg:py-4"
    >
      <span className="mr-2 flex items-center gap-2 lg:mb-4 lg:mr-0 lg:flex-col lg:gap-1">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand">
          <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
            <path
              d="M4 17l5-5 3.5 3L20 7"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span className="font-display text-[10px] font-bold uppercase tracking-[0.18em] text-white/70">
          Trader
        </span>
      </span>

      {(Object.keys(PANELS) as PanelKey[]).map((key) => (
        <button
          key={key}
          onClick={() => scrollTo(PANELS[key].id)}
          className="group flex flex-1 flex-col items-center gap-1 rounded-xl px-2 py-2 transition hover:bg-rail-alt lg:flex-none"
        >
          <span className="relative">
            <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
              <path
                d={ICONS[key]}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-white/75 group-hover:text-white"
              />
            </svg>
          </span>
          <span className="font-display text-[10px] font-semibold tracking-tight text-white/60 group-hover:text-white">
            {PANELS[key].label}
          </span>
          {badges[key] && (
            <span className="rounded-full bg-white/10 px-1.5 text-[9px] font-semibold text-white/70">
              {badges[key]}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}
