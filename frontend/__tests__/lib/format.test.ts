import { describe, expect, it } from "vitest";
import {
  directionGlyph,
  formatPrice,
  formatQuantity,
  formatSignedCurrency,
  formatSignedPercent,
  toneClass,
} from "@/lib/format";

describe("formatPrice", () => {
  it("always shows two decimals", () => {
    expect(formatPrice(190)).toBe("$190.00");
  });

  it("groups thousands", () => {
    expect(formatPrice(10000)).toBe("$10,000.00");
  });
});

describe("formatSignedCurrency", () => {
  it("prefixes a gain with a plus", () => {
    expect(formatSignedCurrency(12.4)).toBe("+$12.40");
  });

  it("prefixes a loss with a minus and no double sign", () => {
    expect(formatSignedCurrency(-12.4)).toBe("-$12.40");
  });

  it("leaves zero unsigned", () => {
    expect(formatSignedCurrency(0)).toBe("$0.00");
  });
});

describe("formatSignedPercent", () => {
  it("signs and rounds to two decimals", () => {
    expect(formatSignedPercent(0.6526)).toBe("+0.65%");
    expect(formatSignedPercent(-1.104)).toBe("-1.10%");
  });
});

describe("formatQuantity", () => {
  it("drops trailing zeros", () => {
    expect(formatQuantity(10)).toBe("10");
    expect(formatQuantity(0.5)).toBe("0.5");
  });

  it("keeps six decimals of precision", () => {
    expect(formatQuantity(1.2345678)).toBe("1.234568");
  });

  it("renders float dust as zero rather than scientific notation", () => {
    expect(formatQuantity(1e-9)).toBe("0");
  });
});

describe("directionGlyph", () => {
  it("pairs a shape with every direction so colour is not the only cue", () => {
    expect(directionGlyph(1)).toBe("▲");
    expect(directionGlyph(-1)).toBe("▼");
    expect(directionGlyph(0)).toBe("–");
  });
});

describe("toneClass", () => {
  it("maps sign to the theme tone", () => {
    expect(toneClass(1)).toContain("up");
    expect(toneClass(-1)).toContain("down");
    expect(toneClass(0)).toContain("flat");
  });
});
