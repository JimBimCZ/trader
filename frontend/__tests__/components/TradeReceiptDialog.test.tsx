import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TradeReceiptDialog } from "@/components/trade/TradeReceiptDialog";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import type { TradeReceipt } from "@/lib/types";

const BUY: TradeReceipt = {
  id: "trade-1",
  ticker: "AAPL",
  side: "buy",
  quantity: 10,
  price: 191.24,
  executedAt: "2026-08-28T09:14:03Z",
  cashBalance: 8087.6,
  position: { quantity: 10, avgCost: 191.24 },
  realizedPnl: null,
  totalValue: 10012.4,
};

const SELL: TradeReceipt = {
  ...BUY,
  id: "trade-2",
  side: "sell",
  realizedPnl: 42.5,
};

function open(receipt: TradeReceipt) {
  usePortfolioStore.setState({ lastTrade: receipt });
}

beforeEach(() => {
  usePortfolioStore.setState({ lastTrade: null, dismissTrade: vi.fn() });
});

it("stays closed until a trade has filled", () => {
  render(<TradeReceiptDialog />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

describe("what it says happened", () => {
  it("names a buy in the tense that is true", () => {
    open(BUY);
    render(<TradeReceiptDialog />);
    expect(screen.getByRole("dialog")).toHaveTextContent("Bought 10 AAPL");
  });

  it("names a sell in the tense that is true", () => {
    open(SELL);
    render(<TradeReceiptDialog />);
    expect(screen.getByRole("dialog")).toHaveTextContent("Sold 10 AAPL");
  });

  it("shows the price the order actually filled at", () => {
    open(BUY);
    render(<TradeReceiptDialog />);
    expect(screen.getByTestId("receipt-price")).toHaveTextContent("$191.24");
  });

  it("shows what the order cost in total", () => {
    open(BUY);
    render(<TradeReceiptDialog />);
    expect(screen.getByTestId("receipt-total")).toHaveTextContent("$1,912.40");
  });

  it("shows the cash left afterwards", () => {
    open(BUY);
    render(<TradeReceiptDialog />);
    expect(screen.getByTestId("receipt-cash")).toHaveTextContent("$8,087.60");
  });
});

describe("realized P&L", () => {
  it("is reported on a sell, with its sign and glyph", () => {
    open(SELL);
    render(<TradeReceiptDialog />);
    const realized = screen.getByTestId("receipt-realized");
    expect(realized).toHaveTextContent("+$42.50");
    expect(realized).toHaveTextContent("▲");
  });

  it("is absent on a buy, which realizes nothing", () => {
    open(BUY);
    render(<TradeReceiptDialog />);
    expect(screen.queryByTestId("receipt-realized")).not.toBeInTheDocument();
  });
});

describe("the position afterwards", () => {
  it("reports the new average cost while shares remain", () => {
    open(BUY);
    render(<TradeReceiptDialog />);
    expect(screen.getByTestId("receipt-position")).toHaveTextContent("$191.24");
  });

  it("says the position closed when the sell took the last share", () => {
    open({ ...SELL, position: null });
    render(<TradeReceiptDialog />);
    expect(screen.getByTestId("receipt-position")).toHaveTextContent(/closed/i);
  });
});

describe("dismissing it", () => {
  it("closes on the Done button", async () => {
    const dismissTrade = vi.fn();
    usePortfolioStore.setState({ dismissTrade });
    open(BUY);

    render(<TradeReceiptDialog />);
    await userEvent.click(screen.getByRole("button", { name: /done/i }));

    expect(dismissTrade).toHaveBeenCalled();
  });

  it("closes on Escape, so a fast trader never has to reach for the mouse", async () => {
    const dismissTrade = vi.fn();
    usePortfolioStore.setState({ dismissTrade });
    open(BUY);

    render(<TradeReceiptDialog />);
    await userEvent.keyboard("{Escape}");

    expect(dismissTrade).toHaveBeenCalled();
  });
});
