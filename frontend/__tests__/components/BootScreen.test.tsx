import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { BOOT_FADE_MS, BootScreen } from "@/components/layout/BootScreen";

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

it("covers the workspace while booting", () => {
  render(<BootScreen done={false} />);
  expect(screen.getByRole("status")).toBeInTheDocument();
});

it("names what it is waiting on, so the wait is not silent to a screen reader", () => {
  render(<BootScreen done={false} />);
  expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
});

it("stays mounted through the fade so the reveal is not a jump cut", () => {
  const { rerender } = render(<BootScreen done={false} />);
  rerender(<BootScreen done />);

  expect(screen.getByRole("status")).toBeInTheDocument();
});

it("stops swallowing clicks the moment the fade starts", () => {
  const { rerender } = render(<BootScreen done={false} />);
  rerender(<BootScreen done />);

  expect(screen.getByRole("status")).toHaveClass("pointer-events-none");
});

it("unmounts once the fade has finished", () => {
  const { rerender } = render(<BootScreen done={false} />);
  rerender(<BootScreen done />);

  act(() => {
    vi.advanceTimersByTime(BOOT_FADE_MS);
  });

  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("never appears when the app is already booted", () => {
  render(<BootScreen done />);

  act(() => {
    vi.advanceTimersByTime(BOOT_FADE_MS);
  });

  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
