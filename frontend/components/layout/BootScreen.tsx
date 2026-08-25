"use client";

import { useEffect, useState } from "react";

/**
 * The cross-fade to the workspace. Kept in sync with `duration-300` below —
 * Tailwind needs the class to be a literal, so the number cannot come from
 * here.
 */
export const BOOT_FADE_MS = 300;

/**
 * Covers the workspace until the calls that decide what the first paint says
 * have answered (see `useAppBoot`). Without it the toolbar reflows as the
 * sign-in control resolves, the portfolio total counts up from $0.00, and the
 * watchlist fills a row at a time.
 *
 * The workspace stays mounted underneath rather than being swapped in on
 * reveal, so the SSE connection and the lazy chart bundles are already warm
 * by the time this lifts.
 */
export function BootScreen({ done }: { done: boolean }) {
  // Unmounted only after the fade — a screen that vanishes on the frame the
  // data lands is a jump cut, which is the thing this exists to avoid.
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (!done) return;
    const timer = setTimeout(() => setGone(true), BOOT_FADE_MS);
    return () => clearTimeout(timer);
  }, [done]);

  if (gone) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="boot-screen"
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center gap-5 bg-bg transition-opacity duration-300 ${
        done ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
    >
      <span className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-blue">
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
        <span className="text-[19px] font-semibold tracking-[-0.02em] text-text">Trader</span>
      </span>

      {/* An indeterminate track rather than a spinner: calmer, and it reads as
          chrome rather than as an alert. `prefers-reduced-motion` leaves the
          fill parked, which still reads as busy without the travel.

          The track is `border` rather than `surfaceSunk`: sunk is #EBEBF0 on a
          #F2F2F7 canvas, which is 1.05:1 — the groove simply is not there in
          light, and the fill reads as a line floating in space. */}
      <span className="h-[3px] w-32 overflow-hidden rounded-full bg-border" aria-hidden="true">
        <span className="boot-track-fill block h-full w-1/2 rounded-full bg-blue" />
      </span>

      <span className="sr-only">Loading your workspace</span>
    </div>
  );
}
