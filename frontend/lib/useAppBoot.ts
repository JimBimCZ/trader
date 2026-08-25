"use client";

import { useEffect, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";

/**
 * How long the boot screen stays up even when everything answers instantly.
 * Locally the four calls settle in ~100ms, and a splash that appears and
 * disappears inside that reads as a flicker rather than as a load.
 */
export const BOOT_MIN_MS = 350;

/**
 * How long the boot screen may hold, however slow the calls are.
 *
 * `allSettled` waits for every call, which is right when they answer and
 * catastrophic when one does not: a cold Neon instance let `GET /api/auth/me`
 * hang until Vercel killed the function at 60s, and the splash sat there for
 * the whole minute. The cap trades a settled first paint for a bounded one:
 * the workspace reveals whether or not every answer is in, and each panel
 * shows what it has as its own call lands.
 */
export const BOOT_MAX_MS = 2_500;

/**
 * Whether the app has enough to paint a settled first screen.
 *
 * The four calls here are the ones whose answers change what the first paint
 * *says*: the session decides whether a sign-in control exists at all (and a
 * zero-config deployment renders none), the portfolio decides the largest
 * number on the page, the watchlist decides the rows, and the chat decides
 * whether the panel opens on history or on the suggested prompts. Prices are
 * deliberately not in the set — they stream in afterwards and flashing is
 * what they are supposed to do.
 *
 * `allSettled`, not `all`: a call that fails must still reveal the app. Every
 * panel already renders its own empty or error state, and any of them beats
 * trapping the user behind a spinner that will never lift.
 */
export function useAppBoot(): boolean {
  const loadSession = useSessionStore((s) => s.load);
  const refreshPortfolio = usePortfolioStore((s) => s.refresh);
  const refreshWatchlist = useWatchlistStore((s) => s.refresh);
  const refreshChat = useChatStore((s) => s.refresh);

  const [booted, setBooted] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const started = Date.now();

    let cap: ReturnType<typeof setTimeout> | undefined;

    // Whichever comes first. The losing promise is not cancelled: a slow call
    // still resolves into its own store, and the panel showing a skeleton for
    // it swaps in the real content whenever that happens.
    void Promise.race([
      Promise.allSettled([loadSession(), refreshPortfolio(), refreshWatchlist(), refreshChat()]),
      new Promise((resolve) => {
        cap = setTimeout(resolve, BOOT_MAX_MS);
      }),
    ]).then(() => {
      if (cancelled) return;
      clearTimeout(cap);
      timer = setTimeout(
        () => setBooted(true),
        Math.max(0, BOOT_MIN_MS - (Date.now() - started)),
      );
    });

    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearTimeout(cap);
    };
    // The store actions are stable for the life of the store, so this is a
    // mount-only effect; listing them would say otherwise.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return booted;
}
