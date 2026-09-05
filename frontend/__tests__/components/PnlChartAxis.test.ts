import { describe, expect, it } from "vitest";
import { axisWidth, valueDomain } from "@/components/portfolio/PnlChart";

/**
 * The band Recharts reserves for the Y axis. Tested directly rather than
 * through the chart, for the same reason the heatmap's colour scale is: the
 * charting library renders to SVG that jsdom cannot measure.
 */

// Recharts clips a label wider than the band, and the failure is silent — the
// dollar sign simply stops being drawn.
const PX_PER_GLYPH = 5.7;
const fits = (label: string, width: number) => label.length * PX_PER_GLYPH <= width;

it("fits the seeded portfolio's labels", () => {
  const width = axisWidth([10_000, 10_000], 0);
  expect(fits("$10,000.00", width)).toBe(true);
});

it("widens for a large account still trading in a narrow range", () => {
  const narrow = axisWidth([10_000, 10_002], 2);
  const large = axisWidth([250_000, 250_002], 2);

  expect(large).toBeGreaterThan(narrow);
  expect(fits("$250,002.00", large)).toBe(true);
});

it("narrows for a small account, giving the width back to the plot", () => {
  expect(axisWidth([500, 502], 2)).toBeLessThan(axisWidth([10_000, 10_002], 2));
});

it("stays compact once the range is wide enough for compact labels", () => {
  // formatCompact takes over past a $50 range, so the labels get shorter even
  // as the values get longer.
  expect(axisWidth([250_000, 400_000], 150_000)).toBeLessThanOrEqual(
    axisWidth([250_000, 250_002], 2),
  );
});

it("never eats more than a quarter of a ~275px card", () => {
  const absurd = axisWidth([98_765_432.1, 98_765_432.2], 0.1);
  expect(absurd).toBeLessThanOrEqual(76);
});

it("keeps a floor so a one-digit series still has a readable gutter", () => {
  expect(axisWidth([1, 2], 1)).toBeGreaterThanOrEqual(44);
});

it("survives an empty series", () => {
  expect(axisWidth([], 0)).toBeGreaterThanOrEqual(44);
});

describe("valueDomain", () => {
  it("pads both ends so the extremes do not touch the plot edges", () => {
    const [low, high] = valueDomain([10_000, 10_100], 10_000);
    expect(low).toBeLessThan(10_000);
    expect(high).toBeGreaterThan(10_100);
  });

  it("keeps the baseline inside the plot when the whole series is above it", () => {
    const [low, high] = valueDomain([10_050, 10_100], 10_000);
    expect(low).toBeLessThan(10_000);
    expect(high).toBeGreaterThan(10_100);
  });

  it("gives a flat series somewhere to sit rather than a zero-height domain", () => {
    const [low, high] = valueDomain([10_000, 10_000], 10_000);
    expect(high).toBeGreaterThan(low);
  });

  it("survives an empty series", () => {
    const [low, high] = valueDomain([], 0);
    expect(high).toBeGreaterThan(low);
  });
});
