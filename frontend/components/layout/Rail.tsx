"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { NAV } from "./panels";

export function Rail() {
  const pathname = usePathname();
  const tickers = useWatchlistStore((s) => s.tickers);
  const positions = usePortfolioStore((s) => s.positions);
  const trades = usePortfolioStore((s) => s.trades);
  const watchlistReady = useWatchlistStore((s) => s.status) === "ready";
  const portfolioReady = usePortfolioStore((s) => s.status) === "ready";
  const tradesReady = usePortfolioStore((s) => s.tradesStatus) === "ready";

  // A count of 0 is a claim, and before the fetch answers it is a wrong one.
  // An em dash says "not known yet" and keeps the badge's width stable.
  const badges: Record<(typeof NAV)[number]["href"], string | undefined> = {
    "/": watchlistReady ? String(tickers.length) : "—",
    "/portfolio/": portfolioReady ? String(positions.length) : "—",
    "/history/": tradesReady ? String(trades.length) : "—",
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

      {NAV.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          id={item.href === "/portfolio/" ? "rail-portfolio" : undefined}
          // The label is hidden below `lg`, which takes it out of the
          // accessibility tree along with the layout.
          aria-label={item.label}
          aria-current={pathname === item.href ? "page" : undefined}
          className={`group flex flex-1 items-center gap-2 rounded-control px-2 py-1.5 text-left transition lg:flex-none ${
            pathname === item.href ? "bg-blue-wash" : "hover:bg-surface-sunk"
          }`}
        >
          <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" aria-hidden="true">
            <path
              d={item.icon}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-blue"
            />
          </svg>
          <span className="hidden text-[13px] font-medium tracking-[-0.01em] text-text lg:block">
            {item.label}
          </span>
          {badges[item.href] && (
            <span className="ml-auto hidden rounded-full bg-surface-sunk px-1.5 py-0.5 text-[10px] font-semibold text-text-muted lg:block">
              {badges[item.href]}
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}
