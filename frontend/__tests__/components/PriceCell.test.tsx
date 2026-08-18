import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { PriceCell } from "@/components/ui/PriceCell";
import { usePriceStore } from "@/lib/stream/priceStore";
import type { PriceSnapshot } from "@/lib/types";

function snapshot(overrides: Partial<PriceSnapshot> = {}): PriceSnapshot {
  return {
    ticker: "AAPL",
    price: 191.24,
    previousPrice: 191.19,
    sessionOpen: 190,
    timestamp: 100,
    dailyChangePercent: 0.65,
    direction: "up",
    ...overrides,
  };
}

beforeEach(() => {
  usePriceStore.setState({ prices: {}, sparklines: {} });
});

describe("PriceCell", () => {
  it("renders a placeholder before any price arrives", () => {
    render(<PriceCell ticker="AAPL" />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders the formatted price", () => {
    usePriceStore.setState({ prices: { AAPL: snapshot() } });
    render(<PriceCell ticker="AAPL" />);
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("$191.24");
  });

  it("flashes up on an uptick", () => {
    usePriceStore.setState({ prices: { AAPL: snapshot({ direction: "up" }) } });
    render(<PriceCell ticker="AAPL" />);
    expect(screen.getByTestId("price-AAPL")).toHaveClass("flash-up");
  });

  it("flashes down on a downtick", () => {
    usePriceStore.setState({ prices: { AAPL: snapshot({ direction: "down" }) } });
    render(<PriceCell ticker="AAPL" />);
    expect(screen.getByTestId("price-AAPL")).toHaveClass("flash-down");
  });

  it("does not flash when unchanged", () => {
    usePriceStore.setState({ prices: { AAPL: snapshot({ direction: "flat" }) } });
    render(<PriceCell ticker="AAPL" />);
    const cell = screen.getByTestId("price-AAPL");
    expect(cell).not.toHaveClass("flash-up");
    expect(cell).not.toHaveClass("flash-down");
  });

  it("subscribes only to its own ticker", () => {
    usePriceStore.setState({ prices: { AAPL: snapshot(), MSFT: snapshot({ ticker: "MSFT" }) } });
    render(<PriceCell ticker="MSFT" />);
    expect(screen.getByTestId("price-MSFT")).toBeInTheDocument();
    expect(screen.queryByTestId("price-AAPL")).not.toBeInTheDocument();
  });
});
