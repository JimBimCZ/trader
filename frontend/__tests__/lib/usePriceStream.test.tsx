import { describe, expect, it, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { usePriceStream, STREAM_URL, STALE_AFTER_MS } from "@/lib/stream/usePriceStream";
import { usePriceStore } from "@/lib/stream/priceStore";
import { FakeEventSource } from "../../vitest.setup";

beforeEach(() => {
  usePriceStore.setState({ prices: {}, sparklines: {}, connectionStatus: "connecting" });
});

const frame = {
  AAPL: {
    ticker: "AAPL",
    price: 191,
    previous_price: 190,
    timestamp: 1,
    session_open: 190,
    change: 1,
    change_percent: 0.5,
    daily_change: 1,
    daily_change_percent: 0.53,
    direction: "up" as const,
  },
};

describe("usePriceStream", () => {
  it("connects to the stream endpoint once", () => {
    renderHook(() => usePriceStream());
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.last.url).toBe(STREAM_URL);
  });

  it("reports open once connected", async () => {
    renderHook(() => usePriceStream());
    act(() => FakeEventSource.last.open());
    await waitFor(() => expect(usePriceStore.getState().connectionStatus).toBe("open"));
  });

  it("applies an incoming frame to the store", async () => {
    renderHook(() => usePriceStream());
    act(() => FakeEventSource.last.emit(frame));
    await waitFor(() => expect(usePriceStore.getState().prices.AAPL.price).toBe(191));
  });

  it("reports reconnecting while the browser retries", async () => {
    renderHook(() => usePriceStream());
    act(() => FakeEventSource.last.fail());
    await waitFor(() => expect(usePriceStore.getState().connectionStatus).toBe("reconnecting"));
  });

  it("reports closed when the connection is given up", async () => {
    renderHook(() => usePriceStream());
    act(() => FakeEventSource.last.fail({ closed: true }));
    await waitFor(() => expect(usePriceStore.getState().connectionStatus).toBe("closed"));
  });

  it("survives a malformed frame", async () => {
    renderHook(() => usePriceStream());
    act(() => FakeEventSource.last.emitRaw("{not json"));
    act(() => FakeEventSource.last.emit(frame));
    await waitFor(() => expect(usePriceStore.getState().prices.AAPL.price).toBe(191));
  });

  it("closes the connection on unmount", () => {
    const { unmount } = renderHook(() => usePriceStream());
    const source = FakeEventSource.last;
    unmount();
    expect(source.closed).toBe(true);
  });
});

describe("staleness watchdog", () => {
  it("reports reconnecting when frames stop arriving", async () => {
    // EventSource does not fire onerror on a stalled connection, so without
    // the watchdog the UI would keep claiming to be live over frozen prices.
    vi.useFakeTimers();
    try {
      renderHook(() => usePriceStream());
      act(() => FakeEventSource.last.open());
      expect(usePriceStore.getState().connectionStatus).toBe("open");

      act(() => {
        vi.advanceTimersByTime(STALE_AFTER_MS + 3_000);
      });

      expect(usePriceStore.getState().connectionStatus).toBe("reconnecting");
    } finally {
      vi.useRealTimers();
    }
  });

  it("stays open while frames keep arriving", () => {
    vi.useFakeTimers();
    try {
      renderHook(() => usePriceStream());
      act(() => FakeEventSource.last.open());

      for (let i = 0; i < 5; i++) {
        act(() => {
          vi.advanceTimersByTime(STALE_AFTER_MS - 2_000);
          FakeEventSource.last.emit(frame);
        });
      }

      expect(usePriceStore.getState().connectionStatus).toBe("open");
    } finally {
      vi.useRealTimers();
    }
  });
});
