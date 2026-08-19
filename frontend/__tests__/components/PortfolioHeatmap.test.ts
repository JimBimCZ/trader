import { describe, expect, it } from "vitest";
import { pnlToColor, pnlOpacity } from "@/components/portfolio/PortfolioHeatmap";
import { palettes } from "@/lib/theme";

/** The colour scale is the risky logic here, not Recharts' rendering. */
const { colors } = palettes.light;

describe("pnlToColor", () => {
  it("maps a gain to the profit end", () => {
    expect(pnlToColor(5)).toBe(colors.heatmapProfitDeep);
  });

  it("maps a loss to the loss end", () => {
    expect(pnlToColor(-5)).toBe(colors.heatmapLossDeep);
  });

  it("treats a negligible move as neutral", () => {
    expect(pnlToColor(0)).toBe(colors.heatmapNeutral);
    expect(pnlToColor(0.05)).toBe(colors.heatmapNeutral);
  });

  it("saturates beyond the clamp so one outlier cannot flatten the rest", () => {
    expect(pnlToColor(200)).toBe(pnlToColor(10));
    expect(pnlToColor(-200)).toBe(pnlToColor(-10));
  });

  it("answers in the appearance it was handed", () => {
    expect(pnlToColor(5, palettes.dark)).toBe(palettes.dark.colors.heatmapProfitDeep);
    expect(pnlToColor(5, palettes.dark)).not.toBe(pnlToColor(5, palettes.light));
  });
});

describe("pnlOpacity", () => {
  it("grows with the magnitude of the move", () => {
    expect(pnlOpacity(10)).toBeGreaterThan(pnlOpacity(1));
  });

  it("stays within a visible range", () => {
    expect(pnlOpacity(0)).toBeGreaterThanOrEqual(0.35);
    expect(pnlOpacity(1000)).toBeLessThanOrEqual(1);
  });

  it("is symmetric in sign", () => {
    expect(pnlOpacity(5)).toBe(pnlOpacity(-5));
  });
});
