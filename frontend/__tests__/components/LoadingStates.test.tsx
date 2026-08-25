import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WatchlistPanel } from "@/components/watchlist/WatchlistPanel";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { AccountMenu } from "@/components/layout/AccountMenu";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";
import { useSessionStore } from "@/store/useSessionStore";
import * as endpoints from "@/lib/api/endpoints";

/**
 * The panels used to have two states, not three: "has data" and "empty".
 * A load still in flight took the empty branch, so a slow start asserted
 * things that were not true -- that the portfolio held no positions, that the
 * watchlist was bare. With the boot screen now capped at 2.5s rather than
 * waiting for every call, that window is reachable in normal use.
 */

// zustand stores are module singletons, so a test that swaps an action for a
// spy leaves that spy in place for every test after it. Captured once, before
// anything can replace them.
const realActions = {
  watchlistRefresh: useWatchlistStore.getState().refresh,
  chatRefresh: useChatStore.getState().refresh,
  portfolioRefresh: usePortfolioStore.getState().refresh,
  portfolioRefreshHistory: usePortfolioStore.getState().refreshHistory,
  sessionLoad: useSessionStore.getState().load,
};

beforeEach(() => {
  usePortfolioStore.setState({
    positions: [],
    status: "pending",
    historyStatus: "pending",
    refresh: realActions.portfolioRefresh,
    refreshHistory: realActions.portfolioRefreshHistory,
  });
  useWatchlistStore.setState({
    tickers: [],
    status: "pending",
    refresh: realActions.watchlistRefresh,
  });
  useChatStore.setState({
    messages: [],
    status: "pending",
    isLoading: false,
    refresh: realActions.chatRefresh,
  });
  useSessionStore.setState({
    session: null,
    providers: [],
    status: "pending",
    load: realActions.sessionLoad,
  });
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
    usePortfolioStore.setState({ positions: [], status: "ready" });
    render(<PositionsTable />);
    expect(screen.getByText(/no open positions/i)).toBeInTheDocument();
  });

  it("says the watchlist is bare, because now it knows", () => {
    useWatchlistStore.setState({ tickers: [], status: "ready" });
    render(<WatchlistPanel />);
    expect(screen.getByText(/nothing on the list yet/i)).toBeInTheDocument();
  });

  it("offers the opening prompts on a genuinely empty conversation", () => {
    useChatStore.setState({ messages: [], status: "ready" });
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
      status: "ready",
    });
    const { container } = render(<AccountMenu />);
    expect(container.querySelector(".skeleton")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign in/i })).not.toBeInTheDocument();
  });
});

describe("when the load was attempted and failed", () => {
  /**
   * The third state, and the reason a boolean was not enough. Flipping
   * `loaded` only on success left the skeleton up for ever; flipping it in a
   * `finally` made the panel assert the data was empty when nobody had
   * managed to read it. Both are wrong, in opposite directions.
   */
  it("does not leave the watchlist skeleton up for ever", () => {
    useWatchlistStore.setState({ tickers: [], status: "failed" });
    const { container } = render(<WatchlistPanel />);
    expect(container.querySelector(".skeleton")).not.toBeInTheDocument();
    expect(screen.getByTestId("load-failure")).toBeInTheDocument();
  });

  it("does not claim the watchlist is empty when the fetch failed", () => {
    useWatchlistStore.setState({ tickers: [], status: "failed" });
    render(<WatchlistPanel />);
    expect(screen.queryByText(/nothing on the list yet/i)).not.toBeInTheDocument();
  });

  it("does not claim the portfolio is empty when the fetch failed", () => {
    usePortfolioStore.setState({ positions: [], status: "failed" });
    render(<PositionsTable />);
    expect(screen.queryByText(/no open positions/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("load-failure")).toBeInTheDocument();
  });

  it("does not offer the opening prompts when history could not be read", () => {
    useChatStore.setState({ messages: [], status: "failed" });
    render(<ChatPanel />);
    expect(screen.queryByRole("button", { name: /how is my portfolio doing/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("load-failure")).toBeInTheDocument();
  });

  it("offers a way back", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    useWatchlistStore.setState({ tickers: [], status: "failed", refresh });
    render(<WatchlistPanel />);

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(refresh).toHaveBeenCalled();
  });
});

describe("the stores record a failure rather than staying pending", () => {
  // The bug the review caught: `useAppBoot` settles the rejection and nothing
  // retries the watchlist or the chat, so a status left at "pending" is a
  // skeleton with no way out.
  it("marks the watchlist failed when its fetch rejects", async () => {
    vi.spyOn(endpoints, "fetchWatchlist").mockRejectedValue(new Error("TIMEOUT"));
    await Promise.allSettled([useWatchlistStore.getState().refresh()]);
    expect(useWatchlistStore.getState().status).toBe("failed");
  });

  it("marks the conversation failed when its fetch rejects", async () => {
    vi.spyOn(endpoints, "fetchChatHistory").mockRejectedValue(new Error("TIMEOUT"));
    await Promise.allSettled([useChatStore.getState().refresh()]);
    expect(useChatStore.getState().status).toBe("failed");
  });

  it("tracks the value history separately from the portfolio summary", async () => {
    // PnlChart draws `history`, fetched from its own endpoint after the boot
    // sequence has already resolved the summary -- so one flag cannot speak
    // for both.
    vi.spyOn(endpoints, "fetchPortfolioHistory").mockRejectedValue(new Error("TIMEOUT"));
    usePortfolioStore.setState({ status: "ready", historyStatus: "pending" });

    await Promise.allSettled([usePortfolioStore.getState().refreshHistory()]);

    expect(usePortfolioStore.getState().status).toBe("ready");
    expect(usePortfolioStore.getState().historyStatus).toBe("failed");
  });
});

describe("the account control", () => {
  it("holds its space while the session is still being fetched", () => {
    useSessionStore.setState({ session: null, providers: [], status: "pending" });
    const { container } = render(<AccountMenu />);
    expect(container.querySelector(".skeleton")).toBeInTheDocument();
  });

  it("renders nothing when the session could not be fetched", () => {
    // A control that cannot say who you are has nothing to offer, and a
    // placeholder for it would never resolve.
    useSessionStore.setState({ session: null, providers: [], status: "failed" });
    const { container } = render(<AccountMenu />);
    expect(container.querySelector(".skeleton")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("records a failed session fetch rather than staying pending", async () => {
    vi.spyOn(endpoints, "fetchSession").mockRejectedValue(new Error("TIMEOUT"));
    await Promise.allSettled([useSessionStore.getState().load()]);
    expect(useSessionStore.getState().status).toBe("failed");
  });
});
