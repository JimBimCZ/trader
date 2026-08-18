"use client";

import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { PANELS, type PanelKey } from "./panels";

/**
 * The sidebar.
 *
 * A macOS source list rather than a dark navigation bar: translucent material
 * over the workspace, its items drawn as quiet rows that tint blue when they
 * are the current one. On a wide screen every panel it lists is already on
 * the page, so each item earns its place by carrying that panel's live count
 * and by scrolling it into view on the narrow layouts, where the workspace
 * stacks.
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

  // Each entry carries its panel's live count, which is what earns the
  // sidebar its place on a wide screen where every panel is already visible.
  const badges: Record<PanelKey, string | undefined> = {
    watchlist: String(tickers.length),
    chart: selected ?? undefined,
    portfolio: String(positions.length),
    assistant: undefined,
  };

  return (
    <nav
      aria-label="Sections"
      className="rise material flex shrink-0 flex-row items-center gap-1 p-2 lg:w-[196px] lg:flex-col lg:items-stretch lg:gap-0.5 lg:p-3"
    >
      <span className="mr-3 flex items-center gap-2 lg:mb-4 lg:mr-0 lg:px-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-[8px] bg-blue">
          <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
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
        <span className="text-[15px] font-semibold tracking-[-0.02em] text-text">Trader</span>
      </span>

      {(Object.keys(PANELS) as PanelKey[]).map((key) => (
        <button
          key={key}
          onClick={() => scrollTo(PANELS[key].id)}
          // The label is display:none below `lg`, which takes it out of the
          // accessibility tree along with the layout — so the name is stated
          // on the button itself rather than left to the text beside it.
          aria-label={PANELS[key].label}
          className="group flex flex-1 items-center gap-2 rounded-control px-2 py-1.5 text-left transition hover:bg-surface-sunk lg:flex-none"
        >
          <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" aria-hidden="true">
            <path
              d={ICONS[key]}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-blue"
            />
          </svg>
          <span className="hidden text-[13px] font-medium tracking-[-0.01em] text-text lg:block">
            {PANELS[key].label}
          </span>
          {badges[key] && (
            <span className="ml-auto hidden rounded-full bg-surface-sunk px-1.5 py-0.5 text-[10px] font-semibold text-text-muted lg:block">
              {badges[key]}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}
