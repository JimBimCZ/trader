import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WatchlistPanel } from "@/components/watchlist/WatchlistPanel";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { AccountMenu } from "@/components/layout/AccountMenu";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";
import { useSessionStore } from "@/store/useSessionStore";

/**
 * The panels used to have two states, not three: "has data" and "empty".
 * A load still in flight took the empty branch, so a slow start asserted
 * things that were not true -- that the portfolio held no positions, that the
 * watchlist was bare. With the boot screen now capped at 2.5s rather than
 * waiting for every call, that window is reachable in normal use.
 */

beforeEach(() => {
  usePortfolioStore.setState({ positions: [], loaded: false });
  useWatchlistStore.setState({ tickers: [], loaded: false });
  useChatStore.setState({ messages: [], loaded: false, isLoading: false });
  useSessionStore.setState({ session: null, providers: [] });
});

describe("while the first load is still in flight", () => {
  it("does not claim the portfolio is empty", () => {
    render(<PositionsTable />);
    expect(screen.queryByText(/no open positions/i)).not.toBeInTheDocument();
  });

  it("does not claim the watchlist is bare", () => {
    render(<WatchlistPanel />);
    expect(screen.queryByText(/nothing on the list yet/i)).not.toBeInTheDocument();
  });

  it("does not offer the opening prompts over unfetched history", () => {
    // A reload with real history would otherwise flash the suggestions first.
    render(<ChatPanel />);
    expect(screen.queryByRole("button", { name: /how is my portfolio doing/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-skeleton")).toBeInTheDocument();
  });

  it("holds the account control's space rather than collapsing it", () => {
    // Returning null here is what made the toolbar reflow when the session
    // landed.
    const { container } = render(<AccountMenu />);
    expect(container.querySelector(".skeleton")).toBeInTheDocument();
  });
});

describe("once the load has answered", () => {
  it("says the portfolio is empty, because now it knows", () => {
    usePortfolioStore.setState({ positions: [], loaded: true });
    render(<PositionsTable />);
    expect(screen.getByText(/no open positions/i)).toBeInTheDocument();
  });

  it("says the watchlist is bare, because now it knows", () => {
    useWatchlistStore.setState({ tickers: [], loaded: true });
    render(<WatchlistPanel />);
    expect(screen.getByText(/nothing on the list yet/i)).toBeInTheDocument();
  });

  it("offers the opening prompts on a genuinely empty conversation", () => {
    useChatStore.setState({ messages: [], loaded: true });
    render(<ChatPanel />);
    expect(screen.queryByTestId("chat-skeleton")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /how is my portfolio doing/i })).toBeInTheDocument();
  });

  it("still renders no sign-in control when no provider is configured", () => {
    // The zero-config path the E2E suite asserts: the placeholder must not
    // turn into a permanent control on a deployment that offers nothing.
    useSessionStore.setState({
      session: {
        id: "u1",
        kind: "guest",
        email: null,
        name: null,
        avatar: null,
        hasActivity: false,
      },
      providers: [],
    });
    const { container } = render(<AccountMenu />);
    expect(container.querySelector(".skeleton")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign in/i })).not.toBeInTheDocument();
  });
});
