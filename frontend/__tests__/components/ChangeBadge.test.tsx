import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChangeBadge } from "@/components/ui/ChangeBadge";

describe("ChangeBadge", () => {
  it("pairs a gain with an up glyph and an explicit sign", () => {
    // Colour alone is not an accessible encoding, so both must be present.
    render(<ChangeBadge value={0.65} testId="badge" />);
    expect(screen.getByTestId("badge")).toHaveTextContent("▲ +0.65%");
  });

  it("pairs a loss with a down glyph", () => {
    render(<ChangeBadge value={-1.1} testId="badge" />);
    expect(screen.getByTestId("badge")).toHaveTextContent("▼ -1.10%");
  });

  it("uses the tone class matching the sign", () => {
    const { rerender } = render(<ChangeBadge value={1} testId="badge" />);
    expect(screen.getByTestId("badge").className).toContain("up");
    rerender(<ChangeBadge value={-1} testId="badge" />);
    expect(screen.getByTestId("badge").className).toContain("down");
  });
});
