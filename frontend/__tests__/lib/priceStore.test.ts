import { beforeEach, describe, expect, it } from "vitest";
import { usePriceStore, normalize, SPARKLINE_POINTS } from "@/lib/stream/priceStore";
import type { RawPriceUpdate } from "@/lib/types";

function raw(overrides: Partial<RawPriceUpdate> = {}): RawPriceUpdate {
  return {
    ticker: "AAPL",
    price: 191.0,
    previous_price: 190.5,
    timestamp: 1_755_500_000,
    session_open: 190.0,
    change: 0.5,
    change_percent: 0.2625,
    daily_change: 1.0,
    daily_change_percent: 0.5263,
    direction: "up",
    ...overrides,
  };
}

beforeEach(() => {
  usePriceStore.setState({ prices: {}, sparklines: {}, connectionStatus: "connecting" });
});

describe("normalize", () => {
  it("reads the daily field, not the tick field", () => {
    // change_percent is tick-over-tick and sits near zero; using it as the
    // daily change is the most likely integration mistake in the app.
    const snapshot = normalize(raw({ change_percent: 0.26, daily_change_percent: 5.5 }));
    expect(snapshot.dailyChangePercent).toBe(5.5);
  });

  it("carries the session baseline through", () => {
    expect(normalize(raw()).sessionOpen).toBe(190.0);
  });

  it("preserves the tick direction for the flash", () => {
    expect(normalize(raw({ direction: "down" })).direction).toBe("down");
  });
});

describe("applyFrame", () => {
  it("stores every ticker in the frame", () => {
    usePriceStore.getState().applyFrame({
      AAPL: raw(),
      MSFT: raw({ ticker: "MSFT", price: 420 }),
    });

    const { prices } = usePriceStore.getState();
    expect(Object.keys(prices).sort()).toEqual(["AAPL", "MSFT"]);
    expect(prices.MSFT.price).toBe(420);
  });

  it("accumulates sparkline points across frames", () => {
    const { applyFrame } = usePriceStore.getState();
    applyFrame({ AAPL: raw({ price: 1 }) });
    applyFrame({ AAPL: raw({ price: 2 }) });
    applyFrame({ AAPL: raw({ price: 3 }) });

    expect(usePriceStore.getState().sparklines.AAPL).toEqual([1, 2, 3]);
  });

  it("caps the sparkline buffer", () => {
    const { applyFrame } = usePriceStore.getState();
    for (let i = 0; i < SPARKLINE_POINTS + 25; i++) {
      applyFrame({ AAPL: raw({ price: i }) });
    }

    const points = usePriceStore.getState().sparklines.AAPL;
    expect(points).toHaveLength(SPARKLINE_POINTS);
    // The newest points survive, the oldest are dropped.
    expect(points[points.length - 1]).toBe(SPARKLINE_POINTS + 24);
  });

  it("replaces a ticker's snapshot rather than merging it", () => {
    const { applyFrame } = usePriceStore.getState();
    applyFrame({ AAPL: raw({ price: 1, direction: "up" }) });
    applyFrame({ AAPL: raw({ price: 2, direction: "down" }) });

    expect(usePriceStore.getState().prices.AAPL.direction).toBe("down");
  });

  it("leaves tickers absent from a frame untouched", () => {
    const { applyFrame } = usePriceStore.getState();
    applyFrame({ AAPL: raw({ price: 1 }), MSFT: raw({ ticker: "MSFT", price: 400 }) });
    applyFrame({ AAPL: raw({ price: 2 }) });

    expect(usePriceStore.getState().prices.MSFT.price).toBe(400);
  });
});

describe("seedSparkline", () => {
  it("seeds from server history and respects the cap", () => {
    const points = Array.from({ length: 200 }, (_, i) => i);
    usePriceStore.getState().seedSparkline("AAPL", points);

    const stored = usePriceStore.getState().sparklines.AAPL;
    expect(stored).toHaveLength(SPARKLINE_POINTS);
    expect(stored[stored.length - 1]).toBe(199);
  });
});
