import { describe, expect, it } from "vitest";
import { palettes, instrumentColor, themeStyleSheet, type Palette } from "@/lib/theme";

/**
 * The accessibility floor, enforced rather than asserted in a comment.
 *
 * §10's rule is that colour is never the only encoding and that every
 * coloured value stays legible. Two appearances doubles the number of
 * foreground/background pairings, and the ones that fail are never the ones
 * anyone remembers to check by eye — systemGreen on white is 1.9:1, which is
 * precisely why the palette carries a separate text-safe variant. This pins
 * that so a future palette edit cannot quietly drop below the line.
 */
function luminance(hex: string): number {
  const channel = (offset: number) => {
    const c = parseInt(hex.slice(1 + offset, 3 + offset), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

function contrast(foreground: string, background: string): number {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Every pairing the app actually renders small text in. */
function pairings({ colors: c }: Palette): [string, string, string][] {
  return [
    ["label on card", c.text, c.surface],
    ["label on canvas", c.text, c.bg],
    ["muted label on card", c.textMuted, c.surface],
    ["muted label on canvas", c.textMuted, c.bg],
    ["muted label on a field", c.textMuted, c.surfaceSunk],
    ["gain on card", c.upText, c.surface],
    ["gain in its pill", c.upText, c.upWash],
    ["loss on card", c.downText, c.surface],
    ["loss in its pill", c.downText, c.downWash],
    ["flat on card", c.flat, c.surface],
    ["flat in its pill", c.flat, c.flatWash],
    ["connecting in its pill", c.yellowText, c.yellowWash],
    ["link on card", c.blueText, c.surface],
    ["tinted button label", c.blueText, c.blueWash],
    ["prominent button label", "#FFFFFF", c.blueFill],
    ["buy button label", "#FFFFFF", c.upFill],
    ["sell button label", "#FFFFFF", c.downFill],
  ];
}

describe.each(["light", "dark"] as const)("the %s palette", (appearance) => {
  const palette = palettes[appearance];

  it.each(pairings(palette))("clears 4.5:1 — %s", (_label, foreground, background) => {
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps every instrument monogram legible on its own chip", () => {
    for (const hue of palette.instruments) {
      expect(contrast(palette.colors.instrumentInk, hue)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("instrumentColor", () => {
  it("gives a symbol the same hue every time", () => {
    expect(instrumentColor("AAPL")).toBe(instrumentColor("AAPL"));
  });

  it("answers from the appearance it was asked about", () => {
    // The light hues are deep enough for white ink and the dark ones bright
    // enough for black, so a symbol cannot wear one set in the other's mode.
    expect(palettes.light.instruments).toContain(instrumentColor("AAPL", "light"));
    expect(palettes.dark.instruments).toContain(instrumentColor("AAPL", "dark"));
  });
});

describe("themeStyleSheet", () => {
  it("emits both appearances, as channel triples an alpha can compose onto", () => {
    const css = themeStyleSheet();
    expect(css).toContain(":root{");
    expect(css).toContain(':root[data-theme="dark"]{');
    // "0 122 255", not "#007AFF" — Tailwind's `bg-blue/15` depends on it.
    expect(css).toContain("--c-blue:0 122 255");
    expect(css).toContain("--c-blue:10 132 255");
  });

  it("declares every token in both appearances, so none can fall back", () => {
    const css = themeStyleSheet();
    const [light, dark] = css.split(':root[data-theme="dark"]');
    const names = (block: string) => (block.match(/--c-[a-z-]+/g) ?? []).sort();
    expect(names(dark)).toEqual(names(light));
    expect(names(light).length).toBeGreaterThan(20);
  });
});
