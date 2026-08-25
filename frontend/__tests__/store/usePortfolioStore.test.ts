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
    vi.spyOn(endpoints, "executeTrade").mockResolvedValue(undefined);
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
    vi.spyOn(endpoints, "executeTrade").mockResolvedValue(undefined);
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
