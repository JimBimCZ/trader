import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Footer } from "@/components/layout/Footer";

describe("Footer", () => {
  it("links to the privacy route", () => {
    render(<Footer />);
    // Either form: `next/link` writes the trailing slash from
    // `trailingSlash: true` at build time, which vitest does not load. The
    // slash is not load-bearing either way -- the backend catch-all resolves
    // both spellings to the same exported page (see backend/tests/test_api.py
    // TestExportedSubroutes), and Vercel's CDN redirects between them.
    const href = screen.getByRole("link", { name: /privacy/i }).getAttribute("href");
    expect(href).toMatch(/^\/privacy\/?$/);
  });

  it("says plainly that the money is not real", () => {
    render(<Footer />);
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent(/simulated/i);
    expect(footer).toHaveTextContent(/not financial advice/i);
  });

  it("keeps its text above the faint tone, which fails the contrast floor", () => {
    // textFaint is 2.9:1 on the light canvas. At 11px this line is exactly
    // the case §10's floor exists for, so it wears the muted tone instead.
    render(<Footer />);
    expect(screen.getByRole("contentinfo").className).not.toContain("text-text-faint");
  });
});
