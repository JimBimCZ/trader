import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TradeBar } from "@/components/trade/TradeBar";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";

beforeEach(() => {
  usePortfolioStore.setState({ tradePending: false, tradeError: null });
  useWatchlistStore.setState({ selectedTicker: "AAPL", tickers: ["AAPL"] });
});

describe("TradeBar", () => {
  it("disables both actions until a quantity is entered", () => {
    render(<TradeBar />);
    expect(screen.getByTestId("buy-button")).toBeDisabled();
    expect(screen.getByTestId("sell-button")).toBeDisabled();
  });

  it("falls back to the selected ticker when the field is blank", async () => {
    const trade = vi.fn().mockResolvedValue(true);
    usePortfolioStore.setState({ trade });

    render(<TradeBar />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "5");
    await userEvent.click(screen.getByTestId("buy-button"));

    expect(trade).toHaveBeenCalledWith("AAPL", "buy", 5);
  });

  it("sends the typed ticker uppercased", async () => {
    const trade = vi.fn().mockResolvedValue(true);
    usePortfolioStore.setState({ trade });
    render(<TradeBar />);

    await userEvent.type(screen.getByTestId("trade-ticker"), "msft");
    await userEvent.type(screen.getByTestId("trade-quantity"), "2");
    await userEvent.click(screen.getByTestId("sell-button"));

    expect(trade).toHaveBeenCalledWith("MSFT", "sell", 2);
  });

  it("rejects a non-positive quantity without calling the API", async () => {
    const trade = vi.fn();
    usePortfolioStore.setState({ trade });
    render(<TradeBar />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "0");
    expect(screen.getByTestId("buy-button")).toBeDisabled();
    expect(trade).not.toHaveBeenCalled();
  });

  it("stays disabled while a trade is in flight", async () => {
    usePortfolioStore.setState({ tradePending: true });
    render(<TradeBar />);
    await userEvent.type(screen.getByTestId("trade-quantity"), "5");
    expect(screen.getByTestId("buy-button")).toBeDisabled();
  });

  it("shows a rejection message from the API", () => {
    usePortfolioStore.setState({ tradeError: "Not enough cash." });
    render(<TradeBar />);
    expect(screen.getByTestId("trade-error")).toHaveTextContent("Not enough cash.");
  });

  it("clears the quantity after a successful trade", async () => {
    usePortfolioStore.setState({ trade: vi.fn().mockResolvedValue(true) });
    render(<TradeBar />);

    const quantity = screen.getByTestId("trade-quantity");
    await userEvent.type(quantity, "5");
    await userEvent.click(screen.getByTestId("buy-button"));

    expect(quantity).toHaveValue(null);
  });
});
