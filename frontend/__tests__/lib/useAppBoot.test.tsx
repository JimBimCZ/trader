import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { BOOT_MAX_MS, BOOT_MIN_MS, useAppBoot } from "@/lib/useAppBoot";
import { useSessionStore } from "@/store/useSessionStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";

/** A promise plus the handles to settle it from the test body. */
function deferred() {
  let resolve!: () => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = () => res();
    reject = rej;
  });
  // Nothing awaits a rejection until the hook does, and an unhandled one
  // fails the run rather than the assertion.
  promise.catch(() => {});
  return { promise, resolve, reject };
}

let session: ReturnType<typeof deferred>;
let portfolio: ReturnType<typeof deferred>;
let watchlist: ReturnType<typeof deferred>;
let chat: ReturnType<typeof deferred>;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  session = deferred();
  portfolio = deferred();
  watchlist = deferred();
  chat = deferred();
  useSessionStore.setState({ load: () => session.promise });
  usePortfolioStore.setState({ refresh: () => portfolio.promise });
  useWatchlistStore.setState({ refresh: () => watchlist.promise });
  useChatStore.setState({ refresh: () => chat.promise });
});

afterEach(() => {
  vi.useRealTimers();
});

/** Settle every boot call, then run out the minimum hold. */
async function settleAll(settle: () => void) {
  await act(async () => {
    settle();
  });
  await act(async () => {
    vi.advanceTimersByTime(BOOT_MIN_MS);
  });
}

it("holds while the boot calls are in flight", async () => {
  const { result } = renderHook(() => useAppBoot());

  await act(async () => {
    portfolio.resolve();
  });

  expect(result.current).toBe(false);
});

it("lifts once every boot call has answered", async () => {
  const { result } = renderHook(() => useAppBoot());

  await settleAll(() => {
    session.resolve();
    portfolio.resolve();
    watchlist.resolve();
    chat.resolve();
  });

  await waitFor(() => expect(result.current).toBe(true));
});

it("lifts even when a boot call fails, so a failure cannot trap the user behind it", async () => {
  const { result } = renderHook(() => useAppBoot());

  await settleAll(() => {
    session.reject(new Error("offline"));
    portfolio.resolve();
    watchlist.reject(new Error("offline"));
    chat.resolve();
  });

  await waitFor(() => expect(result.current).toBe(true));
});

it("holds for the minimum duration so a fast boot does not flicker", async () => {
  const { result } = renderHook(() => useAppBoot());

  await act(async () => {
    session.resolve();
    portfolio.resolve();
    watchlist.resolve();
    chat.resolve();
  });
  await act(async () => {
    vi.advanceTimersByTime(BOOT_MIN_MS - 50);
  });

  expect(result.current).toBe(false);

  await act(async () => {
    vi.advanceTimersByTime(50);
  });

  await waitFor(() => expect(result.current).toBe(true));
});

it("runs the boot calls exactly once", async () => {
  const load = vi.fn().mockResolvedValue(undefined);
  useSessionStore.setState({ load });

  const { rerender } = renderHook(() => useAppBoot());
  rerender();
  rerender();

  expect(load).toHaveBeenCalledTimes(1);
});

it("lifts on the cap even while a call is still hanging", async () => {
  // The failure this exists for: on Vercel a cold Neon instance let
  // `GET /api/auth/me` hang until the platform killed the function at 60s.
  // `allSettled` waits for every call, so the boot screen held for the whole
  // minute. Nothing rejects here -- the promise simply never settles.
  useSessionStore.setState({ load: () => new Promise<void>(() => {}) });
  const { result } = renderHook(() => useAppBoot());

  await act(async () => {
    portfolio.resolve();
    watchlist.resolve();
    chat.resolve();
  });
  await act(async () => {
    vi.advanceTimersByTime(BOOT_MAX_MS);
  });

  await waitFor(() => expect(result.current).toBe(true));
});

it("does not wait for the cap when everything answers promptly", async () => {
  const { result } = renderHook(() => useAppBoot());

  await settleAll(() => {
    session.resolve();
    portfolio.resolve();
    watchlist.resolve();
    chat.resolve();
  });

  // Settled well inside the cap: the floor is what it waited on, not the cap.
  await waitFor(() => expect(result.current).toBe(true));
  expect(BOOT_MIN_MS).toBeLessThan(BOOT_MAX_MS);
});
