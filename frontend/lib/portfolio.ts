/**
 * Valuing the portfolio against the live stream.
 *
 * The header, the positions table, and the heatmap all answer the same
 * question twice a second — what is this holding worth right now, and how far
 * is it from its cost? That is a portfolio rule, not a rendering one, so it
 * lives here where it can be tested without React and cannot drift between the
 * three panels that display it.
 */

import type { Position, PriceSnapshot } from "./types";

export interface Holding {
  ticker: string;
  quantity: number;
  avgCost: number;
  /** The live price, falling back to the REST snapshot until the stream has it. */
  price: number;
  value: number;
  costBasis: number;
  pnl: number;
  /** Return since acquisition, in percent. */
  pctChange: number;
}

export interface Valuation {
  /** Sorted by value, descending — the order every panel displays them in. */
  holdings: Holding[];
  positionsValue: number;
  costBasis: number;
  unrealized: number;
  unrealizedPercent: number;
  /** Positions plus uninvested cash. */
  totalValue: number;
}

export function valueHolding(
  position: Position,
  prices: Record<string, PriceSnapshot>,
): Holding {
  // Prefer the live price so the panels move with the stream between the
  // portfolio's slower REST refreshes.
  const price = prices[position.ticker]?.price ?? position.currentPrice;
  const value = position.quantity * price;
  const costBasis = position.quantity * position.avgCost;

  return {
    ticker: position.ticker,
    quantity: position.quantity,
    avgCost: position.avgCost,
    price,
    value,
    costBasis,
    pnl: value - costBasis,
    pctChange: position.avgCost ? ((price - position.avgCost) / position.avgCost) * 100 : 0,
  };
}

export function valuePortfolio(
  positions: Position[],
  prices: Record<string, PriceSnapshot>,
  cash: number,
): Valuation {
  const holdings = positions.map((position) => valueHolding(position, prices));

  let positionsValue = 0;
  let costBasis = 0;
  for (const holding of holdings) {
    positionsValue += holding.value;
    costBasis += holding.costBasis;
  }

  const unrealized = positionsValue - costBasis;

  return {
    holdings: holdings.sort((a, b) => b.value - a.value),
    positionsValue,
    costBasis,
    unrealized,
    unrealizedPercent: costBasis ? (unrealized / costBasis) * 100 : 0,
    totalValue: cash + positionsValue,
  };
}
