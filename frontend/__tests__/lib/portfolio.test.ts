import { describe, expect, it } from "vitest";
import { valueHolding, valuePortfolio } from "@/lib/portfolio";
import type { Position, PriceSnapshot } from "@/lib/types";

function position(ticker: string, quantity: number, avgCost: number, currentPrice: number): Position {
  return {
    ticker,
    quantity,
    avgCost,
    currentPrice,
    marketValue: quantity * currentPrice,
    unrealizedPnl: (currentPrice - avgCost) * quantity,
    pctChange: avgCost ? ((currentPrice - avgCost) / avgCost) * 100 : 0,
  };
}

function price(ticker: string, value: number): PriceSnapshot {
  return {
    ticker,
    price: value,
    previousPrice: value,
    sessionOpen: value,
    timestamp: 0,
    dailyChangePercent: 0,
    direction: "flat",
  };
}

describe("valueHolding", () => {
  it("values against the live price when the stream has one", () => {
    const holding = valueHolding(position("AAPL", 10, 100, 105), { AAPL: price("AAPL", 200) });

    expect(holding.price).toBe(200);
    expect(holding.value).toBe(2000);
    expect(holding.costBasis).toBe(1000);
    expect(holding.pnl).toBe(1000);
    expect(holding.pctChange).toBe(100);
  });

  it("falls back to the REST snapshot until the stream carries the ticker", () => {
    const holding = valueHolding(position("AAPL", 10, 100, 105), {});

    expect(holding.price).toBe(105);
    expect(holding.pnl).toBeCloseTo(50);
  });

  it("reports a loss as a negative return", () => {
    const holding = valueHolding(position("TSLA", 4, 250, 250), { TSLA: price("TSLA", 200) });

    expect(holding.pnl).toBe(-200);
    expect(holding.pctChange).toBe(-20);
  });

  it("does not divide by a zero cost basis", () => {
    const holding = valueHolding(position("FREE", 5, 0, 10), {});

    expect(holding.pctChange).toBe(0);
  });
});

describe("valuePortfolio", () => {
  const positions = [position("AAPL", 10, 100, 100), position("NVDA", 2, 50, 50)];

  it("adds cash to the position value for the account total", () => {
    const { positionsValue, totalValue } = valuePortfolio(positions, {}, 500);

    expect(positionsValue).toBe(1100);
    expect(totalValue).toBe(1600);
  });

  it("derives unrealized P&L against the whole cost basis", () => {
    const prices = { AAPL: price("AAPL", 110), NVDA: price("NVDA", 50) };
    const { costBasis, unrealized, unrealizedPercent } = valuePortfolio(positions, prices, 0);

    expect(costBasis).toBe(1100);
    expect(unrealized).toBeCloseTo(100);
    expect(unrealizedPercent).toBeCloseTo(9.0909, 3);
  });

  it("orders holdings by value so every panel lists them the same way", () => {
    const prices = { AAPL: price("AAPL", 1), NVDA: price("NVDA", 500) };
    const { holdings } = valuePortfolio(positions, prices, 0);

    expect(holdings.map((h) => h.ticker)).toEqual(["NVDA", "AAPL"]);
  });

  it("is all cash when nothing is held", () => {
    const { holdings, unrealized, unrealizedPercent, totalValue } = valuePortfolio([], {}, 10_000);

    expect(holdings).toEqual([]);
    expect(unrealized).toBe(0);
    expect(unrealizedPercent).toBe(0);
    expect(totalValue).toBe(10_000);
  });
});
