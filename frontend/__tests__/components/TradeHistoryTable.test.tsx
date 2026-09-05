import { beforeEach, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { TradeHistoryTable } from "@/components/portfolio/TradeHistoryTable";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import type { TradeRecord } from "@/lib/types";

const sell: TradeRecord = {
  id: "t1", ticker: "NVDA", side: "sell", quantity: 4, price: 874.5,
  executedAt: "2026-09-05T14:32:07Z", value: 3498, realizedPnl: 212.4,
};
const buy: TradeRecord = {
  id: "t2", ticker: "AAPL", side: "buy", quantity: 12, price: 190.11,
  executedAt: "2026-09-05T14:28:51Z", value: 2281.32, realizedPnl: null,
};

beforeEach(() => {
  usePortfolioStore.setState({
    trades: [sell, buy],
    tradesStatus: "ready",
    refreshTrades: async () => {},
  });
});

it("names each side in the tense that is true", () => {
  render(<TradeHistoryTable />);
  expect(screen.getByText("Sold")).toBeInTheDocument();
  expect(screen.getByText("Bought")).toBeInTheDocument();
});

it("carries a sign and a glyph on a realized value, so colour is never the only encoding", () => {
  render(<TradeHistoryTable />);
  const row = screen.getByRole("row", { name: /NVDA/ });
  expect(within(row).getByText(/▲/)).toBeInTheDocument();
  expect(within(row).getByText(/\+\$212\.40/)).toBeInTheDocument();
});

it("prints an em dash on a buy rather than a zero that reads as break-even", () => {
  render(<TradeHistoryTable />);
  const row = screen.getByRole("row", { name: /AAPL/ });
  expect(within(row).getByText("—")).toBeInTheDocument();
});

it("says so when there is nothing to show", () => {
  usePortfolioStore.setState({ trades: [], tradesStatus: "ready" });
  render(<TradeHistoryTable />);
  expect(screen.getByText(/no trades yet/i)).toBeInTheDocument();
});

it("offers a retry when the log could not be loaded", () => {
  usePortfolioStore.setState({ trades: [], tradesStatus: "failed" });
  render(<TradeHistoryTable />);
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
});
