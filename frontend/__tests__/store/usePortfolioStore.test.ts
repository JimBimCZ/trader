import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { ApiError } from "@/lib/api/client";
import * as endpoints from "@/lib/api/endpoints";

/**
 * `trade()` does three things in sequence: place the order, then re-read the
 * portfolio and the value history. Only the first can fail the trade. The
 * other two are re-reads of a result the server has already committed, and
 * treating their failure as a rejected order is a lie about money that has
 * already moved -- one that invites the user to place the same order twice.
 */

/** A fill the server accepted, as `executeTrade` hands it back. */
const FILLED = {
  id: "trade-1",
  ticker: "AAPL",
  side: "buy" as const,
  quantity: 10,
  price: 191.24,
  executedAt: "2026-08-28T09:14:03Z",
  cashBalance: 8087.6,
  position: { quantity: 10, avgCost: 191.24 },
  realizedPnl: null,
  totalValue: 10012.4,
};

const realRefresh = usePortfolioStore.getState().refresh;
const realRefreshHistory = usePortfolioStore.getState().refreshHistory;

beforeEach(() => {
  usePortfolioStore.setState({
    positions: [],
    status: "ready",
    historyStatus: "ready",
    tradeError: null,
    tradePending: false,
    refresh: realRefresh,
    refreshHistory: realRefreshHistory,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("a trade that the server accepted", () => {
  beforeEach(() => {
    vi.spyOn(endpoints, "executeTrade").mockResolvedValue(FILLED);
  });

  it("is reported as filled even when the portfolio re-read fails", async () => {
    vi.spyOn(endpoints, "fetchPortfolio").mockRejectedValue(new Error("TIMEOUT"));
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockResolvedValue([]);

    await expect(usePortfolioStore.getState().trade("AAPL", "buy", 1)).resolves.toBe(true);
  });

  it("does not claim the trade could not be completed", async () => {
    vi.spyOn(endpoints, "fetchPortfolio").mockRejectedValue(new Error("TIMEOUT"));
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockResolvedValue([]);

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(usePortfolioStore.getState().tradeError).toBeNull();
  });

  it("is reported as filled even when the history re-read fails", async () => {
    vi.spyOn(endpoints, "fetchPortfolio").mockResolvedValue({
      cashBalance: 100,
      positions: [],
      positionsValue: 0,
      totalValue: 100,
      unrealizedPnl: 0,
    });
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockRejectedValue(new Error("TIMEOUT"));

    await expect(usePortfolioStore.getState().trade("AAPL", "buy", 1)).resolves.toBe(true);
    expect(usePortfolioStore.getState().tradeError).toBeNull();
  });

  it("still surfaces the stale screen through the panels' own load state", async () => {
    // The failure is not silently swallowed -- it becomes the thing the
    // positions panel renders, with its own Retry.
    vi.spyOn(endpoints, "fetchPortfolio").mockRejectedValue(new Error("TIMEOUT"));
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockRejectedValue(new Error("TIMEOUT"));

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(usePortfolioStore.getState().status).toBe("failed");
    expect(usePortfolioStore.getState().historyStatus).toBe("failed");
  });

  it("attempts both re-reads even when the first one fails", async () => {
    vi.spyOn(endpoints, "fetchPortfolio").mockRejectedValue(new Error("TIMEOUT"));
    const history = vi.spyOn(endpoints, "fetchPortfolioHistory").mockResolvedValue([]);

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(history).toHaveBeenCalled();
  });
});

describe("a trade the server refused", () => {
  it("is reported as failed, with the server's reason", async () => {
    vi.spyOn(endpoints, "executeTrade").mockRejectedValue(
      new ApiError("INSUFFICIENT_CASH", "Not enough cash for that order.", 400),
    );

    await expect(usePortfolioStore.getState().trade("AAPL", "buy", 1e9)).resolves.toBe(false);
    expect(usePortfolioStore.getState().tradeError).toBe("Not enough cash for that order.");
  });

  it("does not re-read a portfolio that cannot have changed", async () => {
    vi.spyOn(endpoints, "executeTrade").mockRejectedValue(
      new ApiError("INSUFFICIENT_CASH", "Not enough cash.", 400),
    );
    const portfolio = vi.spyOn(endpoints, "fetchPortfolio");

    await usePortfolioStore.getState().trade("AAPL", "buy", 1e9);

    expect(portfolio).not.toHaveBeenCalled();
  });

  it("falls back to its own wording when the failure carries none", async () => {
    vi.spyOn(endpoints, "executeTrade").mockRejectedValue(new TypeError("Failed to fetch"));

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(usePortfolioStore.getState().tradeError).toBe("The trade could not be completed.");
  });
});

describe("the pending flag", () => {
  it("clears after a fill whose re-read failed", async () => {
    vi.spyOn(endpoints, "executeTrade").mockResolvedValue(FILLED);
    vi.spyOn(endpoints, "fetchPortfolio").mockRejectedValue(new Error("TIMEOUT"));
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockRejectedValue(new Error("TIMEOUT"));

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(usePortfolioStore.getState().tradePending).toBe(false);
  });

  it("clears after a refused order", async () => {
    vi.spyOn(endpoints, "executeTrade").mockRejectedValue(
      new ApiError("INSUFFICIENT_CASH", "Nope.", 400),
    );

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(usePortfolioStore.getState().tradePending).toBe(false);
  });
});

/**
 * The receipt the trade ticket shows after a fill.
 *
 * Taken from the trade response rather than from the re-reads that follow
 * it: those describe the portfolio *now*, which is not what the user just
 * did, and either of them can fail without the fill being any less real.
 */
describe("the receipt a filled trade leaves behind", () => {
  beforeEach(() => {
    usePortfolioStore.setState({ lastTrade: null });
    vi.spyOn(endpoints, "executeTrade").mockResolvedValue(FILLED);
    vi.spyOn(endpoints, "fetchPortfolio").mockResolvedValue({
      cashBalance: 8087.6,
      positions: [],
      positionsValue: 0,
      totalValue: 10012.4,
      unrealizedPnl: 0,
    });
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockResolvedValue([]);
  });

  it("carries what the server said it filled", async () => {
    await usePortfolioStore.getState().trade("AAPL", "buy", 10);
    expect(usePortfolioStore.getState().lastTrade).toEqual(FILLED);
  });

  it("survives a portfolio re-read that failed", async () => {
    vi.spyOn(endpoints, "fetchPortfolio").mockRejectedValue(new Error("TIMEOUT"));

    await usePortfolioStore.getState().trade("AAPL", "buy", 10);

    expect(usePortfolioStore.getState().lastTrade).toEqual(FILLED);
  });

  it("is not left behind by an order the server rejected", async () => {
    vi.spyOn(endpoints, "executeTrade").mockRejectedValue(
      new ApiError("INSUFFICIENT_CASH", "Not enough cash.", 400),
    );

    await usePortfolioStore.getState().trade("AAPL", "buy", 10);

    expect(usePortfolioStore.getState().lastTrade).toBeNull();
  });

  it("is cleared when the user dismisses it", async () => {
    await usePortfolioStore.getState().trade("AAPL", "buy", 10);

    usePortfolioStore.getState().dismissTrade();

    expect(usePortfolioStore.getState().lastTrade).toBeNull();
  });
});

/**
 * The trade log, fetched by its own page rather than by the boot sequence --
 * see `tradesStatus` on the store.
 */
describe("the trade log", () => {
  it("records a failed trade-log fetch rather than leaving it pending", async () => {
    vi.spyOn(endpoints, "fetchTrades").mockRejectedValueOnce(new Error("offline"));

    await expect(usePortfolioStore.getState().refreshTrades()).rejects.toThrow();
    expect(usePortfolioStore.getState().tradesStatus).toBe("failed");
  });

  it("refreshes the trade log after a fill, so history is current", async () => {
    // `FILLED` is the same fixture the receipt tests above use for a fill
    // `executeTrade` hands back.
    vi.spyOn(endpoints, "executeTrade").mockResolvedValueOnce(FILLED);
    vi.spyOn(endpoints, "fetchPortfolio").mockResolvedValue({
      cashBalance: 8087.6,
      positions: [],
      positionsValue: 0,
      totalValue: 10012.4,
      unrealizedPnl: 0,
    });
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockResolvedValue([]);
    const trades = vi.spyOn(endpoints, "fetchTrades").mockResolvedValue([]);

    await usePortfolioStore.getState().trade("AAPL", "buy", 1);

    expect(trades).toHaveBeenCalled();
  });
});
