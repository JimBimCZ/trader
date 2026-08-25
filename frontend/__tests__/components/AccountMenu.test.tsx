import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AccountMenu } from "@/components/layout/AccountMenu";
import { useSessionStore } from "@/store/useSessionStore";

function setSession(overrides = {}) {
  useSessionStore.setState({
    session: {
      id: "u1", kind: "guest", email: null, name: null,
      avatar: null, hasActivity: false, ...overrides,
    },
    providers: [{ name: "google", label: "Google" }],
    sessionVersion: 0,
  });
}

beforeEach(() => {
  useSessionStore.setState({ session: null, providers: [], sessionVersion: 0 });
});

describe("as a guest", () => {
  it("offers sign in", () => {
    setSession();
    render(<AccountMenu />);
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("says what is at stake once there is something to lose", () => {
    // The hint is the whole reason a guest would sign in; showing it to a
    // guest with an empty portfolio is noise on first paint.
    setSession({ hasActivity: true });
    render(<AccountMenu />);
    expect(screen.getByText(/sign in to keep this portfolio/i)).toBeInTheDocument();
  });

  it("stays quiet on a fresh visit", () => {
    setSession({ hasActivity: false });
    render(<AccountMenu />);
    expect(screen.queryByText(/sign in to keep this portfolio/i)).not.toBeInTheDocument();
  });

  it("lists the configured providers when opened", async () => {
    setSession();
    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByRole("link", { name: /continue with google/i })).toHaveAttribute(
      "href",
      "/api/auth/login/google",
    );
  });

  it("renders no sign-in control when no provider is configured", () => {
    // The zero-config quick start: a button that dead-ends is worse than none.
    setSession();
    useSessionStore.setState({ providers: [] });
    render(<AccountMenu />);
    expect(screen.queryByRole("button", { name: /sign in/i })).not.toBeInTheDocument();
  });
});

describe("as a signed-in user", () => {
  it("shows the account and can sign out", async () => {
    const signOut = vi.fn();
    setSession({ kind: "user", email: "ada@example.com", name: "Ada" });
    useSessionStore.setState({ signOut });

    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: /ada/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));

    expect(signOut).toHaveBeenCalled();
  });

  it("falls back to the email when the provider gave no name", () => {
    setSession({ kind: "user", email: "ada@example.com", name: null });
    render(<AccountMenu />);
    expect(screen.getByRole("button", { name: /ada@example.com/i })).toBeInTheDocument();
  });

  it("falls back to the monogram when the avatar fails to load", () => {
    // A 404, a hotlink block, or an expired token all fail silently as far
    // as React is concerned -- only the <img>'s own error event catches it.
    setSession({
      kind: "user",
      email: "ada@example.com",
      name: "Ada",
      avatar: "https://example.com/broken.jpg",
    });
    render(<AccountMenu />);

    const avatar = screen.getByTestId("account-avatar");
    fireEvent.error(avatar);

    expect(screen.queryByTestId("account-avatar")).not.toBeInTheDocument();
    expect(screen.getByText("A", { selector: "span[aria-hidden]" })).toBeInTheDocument();
  });
});
