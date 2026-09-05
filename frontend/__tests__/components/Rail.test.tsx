import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Rail } from "@/components/layout/Rail";

vi.mock("next/navigation", () => ({ usePathname: () => "/portfolio/" }));

it("marks the route being viewed", () => {
  render(<Rail />);
  expect(screen.getByRole("link", { name: /portfolio/i })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: /overview/i })).not.toHaveAttribute("aria-current");
});

it("links to all three workspace routes", () => {
  render(<Rail />);
  // `next/link` only writes the trailing slash from `trailingSlash: true` at
  // build time, which vitest does not load -- see Footer.test.tsx for the
  // same quirk. The slash is not load-bearing either way.
  expect(screen.getByRole("link", { name: /overview/i })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: /portfolio/i }).getAttribute("href")).toMatch(
    /^\/portfolio\/?$/,
  );
  expect(screen.getByRole("link", { name: /history/i }).getAttribute("href")).toMatch(
    /^\/history\/?$/,
  );
});
