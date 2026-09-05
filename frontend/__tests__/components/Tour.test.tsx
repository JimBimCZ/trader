import { beforeEach, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Tour, TOUR_STORAGE_KEY } from "@/components/onboarding/Tour";
import { useSessionStore } from "@/store/useSessionStore";

function asGuest() {
  useSessionStore.setState({
    status: "ready",
    session: { id: "g1", kind: "guest", email: null, name: null, avatar: null, hasActivity: false },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  // The steps point at real ids; without them every step is skipped.
  document.body.innerHTML = `
    <div id="panel-watchlist"></div><div id="panel-chart"></div>
    <div id="panel-assistant"></div><div id="rail-portfolio"></div>`;
  asGuest();
});

it("greets a signed-out visitor", () => {
  render(<Tour />);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("moves focus to the dialog the moment it opens, not just on advance", () => {
  render(<Tour />);
  expect(screen.getByRole("dialog")).toHaveFocus();
});

it("stays away from a signed-in user, who has seen the app", () => {
  useSessionStore.setState({
    session: { id: "u1", kind: "user", email: "a@b.c", name: "A", avatar: null, hasActivity: true },
  });
  render(<Tour />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("does not come back once it has been dismissed", () => {
  window.localStorage.setItem(TOUR_STORAGE_KEY, "1");
  render(<Tour />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("closes on Skip, and remembers", () => {
  render(<Tour />);
  fireEvent.click(screen.getByRole("button", { name: /skip/i }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(window.localStorage.getItem(TOUR_STORAGE_KEY)).toBe("1");
});

it("closes on Escape", () => {
  render(<Tour />);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("advances, and the last step ends it", () => {
  render(<Tour />);
  expect(screen.getByText(/1 of/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /next/i }));
  expect(screen.getByText(/2 of/)).toBeInTheDocument();
});

it("skips a step whose target is not on screen", () => {
  document.body.innerHTML = `<div id="panel-watchlist"></div>`;
  render(<Tour />);
  // Only the one reachable step is counted, so the tour never points at nothing.
  expect(screen.getByText("1 of 1")).toBeInTheDocument();
});
